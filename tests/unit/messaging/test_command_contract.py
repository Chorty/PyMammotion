"""Reply identity, result validation and replay policy for ``send_and_wait`` (G04).

Replies are real ``LubaMsg`` frames routed through the real broker; only the device's
send path is replaced, so these pin what reaches ``on_message`` and how many times a
command leaves.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.device.handle import DeviceHandle
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.messaging.broker import DeviceMessageBroker
from pymammotion.messaging.command_contract import DEFAULT_ATTEMPTS, NO_REPLAY_COMMANDS, contract_for
from pymammotion.proto import LubaMsg, MctlNav, MctlSys, NavTaskCtrlAck, ReportInfoData
from pymammotion.transport.base import (
    CommandRejectedError,
    CommandResultError,
    CommandTimeoutError,
    ConcurrentRequestError,
)
from tests._helpers import make_bare_client, make_mock_handle, wait_until

_NAME = "Luba-VSG04TST"
_FIELD = "todev_taskctrl_ack"
_WAIT = 0.05
#: ``cancel_job`` and ``pause_execute_task`` are task type 1, actions 4 and 2.
_CANCEL = (1, 4)
_PAUSE = (1, 2)


def ack(task: tuple[int, int], result: int = 0) -> LubaMsg:
    """Return the task-control acknowledgement the device sends for *task*."""
    task_type, action = task
    return LubaMsg(nav=MctlNav(todev_taskctrl_ack=NavTaskCtrlAck(type=task_type, action=action, result=result)))


def report() -> LubaMsg:
    """Return an unrelated unsolicited frame."""
    return LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData()))


async def device(*replies: LubaMsg) -> tuple[MammotionClient, DeviceHandle, list[bytes]]:
    """Register a handle whose device answers each send with the next of *replies*."""
    client = make_bare_client()
    handle = make_mock_handle(device_name=_NAME)
    await client._device_registry.register(handle)  # noqa: SLF001
    sent: list[bytes] = []
    queued = list(replies)

    async def send_raw(payload: bytes, **_kwargs: object) -> None:
        sent.append(payload)
        if queued:
            reply = queued.pop(0)
            asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(handle.broker.on_message(reply)))

    handle.send_raw = AsyncMock(side_effect=send_raw)  # type: ignore[method-assign]
    return client, handle, sent


def unsolicited(broker: DeviceMessageBroker) -> list[object]:
    """Collect what the broker hands to the event bus."""
    seen: list[object] = []

    async def collect(message: object) -> None:
        seen.append(message)

    broker.subscribe_unsolicited(collect)
    return seen


# --------------------------------------------------------------------- policy table


def test_every_no_replay_command_is_a_real_builder() -> None:
    """A typo in the table would silently leave that command replayable."""
    assert sorted(key for key in NO_REPLAY_COMMANDS if not hasattr(MammotionCommand, key)) == []


def test_task_control_contract_is_derived_from_the_sent_bytes() -> None:
    commands = MammotionCommand(_NAME, user_account=1)
    contract = contract_for("cancel_job", _FIELD, commands.cancel_job())

    assert contract.attempts == 1
    assert contract.match is not None
    assert contract.match(ack(_CANCEL)) is True
    assert contract.match(ack(_PAUSE)) is False
    assert contract.match(ack((3, 4))) is False
    assert contract.match(report()) is False


def test_reads_keep_the_historical_retry() -> None:
    commands = MammotionCommand(_NAME, user_account=1)
    contract = contract_for("get_device_version_main", "toapp_devinfo_resp", commands.get_device_version_main())

    assert (contract.attempts, contract.match, contract.result) == (DEFAULT_ATTEMPTS, None, None)


# --------------------------------------------------------------------- client contract


async def test_matching_ack_with_zero_result_returns_the_reply() -> None:
    client, _handle, sent = await device(ack(_CANCEL))

    reply = await client.send_command_and_wait(_NAME, "cancel_job", _FIELD, send_timeout=1.0)

    assert reply.nav.todev_taskctrl_ack.action == 4
    assert len(sent) == 1


@pytest.mark.regression
@pytest.mark.parametrize("result", [-1142, 37])
async def test_nonzero_result_raises_and_keeps_the_raw_code(result: int) -> None:
    """A refused task control used to return as though it had been accepted."""
    client, _handle, _sent = await device(ack(_CANCEL, result=result))

    with pytest.raises(CommandResultError) as raised:
        await client.send_command_and_wait(_NAME, "cancel_job", _FIELD, send_timeout=1.0)

    assert isinstance(raised.value, CommandRejectedError)
    assert (raised.value.expected_field, raised.value.result) == (_FIELD, result)
    assert raised.value.reply.nav.todev_taskctrl_ack.result == result


@pytest.mark.regression
async def test_wrong_action_ack_does_not_complete_and_stays_unsolicited() -> None:
    """A pause ack used to complete a pending cancel and vanish from the event bus."""
    client, handle, sent = await device(ack(_PAUSE))
    seen = unsolicited(handle.broker)

    with pytest.raises(CommandTimeoutError):
        await client.send_command_and_wait(_NAME, "cancel_job", _FIELD, send_timeout=_WAIT)

    assert len(sent) == 1
    assert [m.nav.todev_taskctrl_ack.action for m in seen] == [2]
    assert handle.broker._pending == {}  # noqa: SLF001


@pytest.mark.regression
@pytest.mark.parametrize(
    ("key", "field"),
    [
        ("cancel_job", _FIELD),
        ("leave_dock", _FIELD),
        # The base waits on the message type name; the oneof field is zone_start_precent,
        # so this reply can never match and the job start was always sent twice.
        ("start_job", "zone_start_precent_t"),
        ("set_blade_control", "toapp_knife_status_change"),
    ],
)
async def test_actions_are_sent_once_after_an_unanswered_wait(key: str, field: str) -> None:
    """Each of these was resent after the first reply window, changing physical state twice."""
    client, _handle, sent = await device()
    kwargs = {"on_off": 1} if key == "set_blade_control" else {}

    with pytest.raises(CommandTimeoutError) as raised:
        await client.send_command_and_wait(_NAME, key, field, send_timeout=_WAIT, **kwargs)

    assert len(sent) == 1
    assert raised.value.attempts == 1


@pytest.mark.regression
async def test_stalled_action_send_is_not_resent() -> None:
    """A send that outlived its deadline may still have reached the mower."""
    client, handle, _sent = await device()
    sends = 0

    async def stall(*_args: object, **_kwargs: object) -> None:
        nonlocal sends
        sends += 1
        await asyncio.sleep(1.0)

    handle.send_raw = AsyncMock(side_effect=stall)  # type: ignore[method-assign]

    with pytest.raises(CommandTimeoutError):
        await client.send_command_and_wait(_NAME, "cancel_job", _FIELD, send_timeout=_WAIT)

    assert sends == 1


@pytest.mark.parametrize("key", ["get_device_version_main", "get_report_cfg"])
async def test_reads_are_still_retried(key: str) -> None:
    client, _handle, sent = await device()

    with pytest.raises(CommandTimeoutError):
        await client.send_command_and_wait(_NAME, key, "toapp_devinfo_resp", send_timeout=_WAIT)

    assert len(sent) == DEFAULT_ATTEMPTS


# --------------------------------------------------------------------- broker seam


async def test_matcher_failure_is_a_non_match_and_never_breaks_routing() -> None:
    broker = DeviceMessageBroker()
    seen = unsolicited(broker)

    def broken(_message: object) -> bool:
        raise AttributeError("matcher bug")

    async def deliver() -> None:
        await wait_until(lambda: _FIELD in broker._pending)  # noqa: SLF001
        await broker.on_message(ack(_CANCEL))

    delivery = asyncio.ensure_future(deliver())
    with pytest.raises(CommandTimeoutError):
        await broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=_WAIT, retries=1, match=broken)
    await delivery

    assert len(seen) == 1
    assert broker._pending == {}  # noqa: SLF001


@pytest.mark.regression
async def test_late_ack_cannot_complete_a_newer_request_for_another_action() -> None:
    """A cancel ack arriving after its request timed out used to complete the next pause."""
    broker = DeviceMessageBroker()
    seen = unsolicited(broker)
    commands = MammotionCommand(_NAME, user_account=1)
    cancel = contract_for("cancel_job", _FIELD, commands.cancel_job())
    pause = contract_for("pause_execute_task", _FIELD, commands.pause_execute_task())

    with pytest.raises(CommandTimeoutError):
        await broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=_WAIT, retries=1, match=cancel.match)

    async def late_then_real() -> None:
        await wait_until(lambda: _FIELD in broker._pending)  # noqa: SLF001
        await broker.on_message(ack(_CANCEL))
        await broker.on_message(ack(_PAUSE))

    delivery = asyncio.ensure_future(late_then_real())
    reply = await broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=1.0, retries=1, match=pause.match)
    await delivery

    assert reply.nav.todev_taskctrl_ack.action == 2
    assert [m.nav.todev_taskctrl_ack.action for m in seen] == [4]


async def test_identical_action_replies_remain_ambiguous() -> None:
    """Documented limit: with no request ID, a delayed ack for one cancel completes the next."""
    broker = DeviceMessageBroker()
    commands = MammotionCommand(_NAME, user_account=1)
    cancel = contract_for("cancel_job", _FIELD, commands.cancel_job())

    with pytest.raises(CommandTimeoutError):
        await broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=_WAIT, retries=1, match=cancel.match)

    async def delayed_first_ack() -> None:
        await wait_until(lambda: _FIELD in broker._pending)  # noqa: SLF001
        await broker.on_message(ack(_CANCEL))

    delivery = asyncio.ensure_future(delayed_first_ack())
    reply = await broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=1.0, retries=1, match=cancel.match)
    await delivery

    assert reply.nav.todev_taskctrl_ack.action == 4


async def test_concurrent_requests_keep_their_own_replies_and_one_per_field() -> None:
    broker = DeviceMessageBroker()

    async def answer() -> None:
        await wait_until(lambda: {_FIELD, "toapp_report_data"} <= set(broker._pending))  # noqa: SLF001
        with pytest.raises(ConcurrentRequestError):
            await broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=_WAIT, retries=1)
        await broker.on_message(report())
        await broker.on_message(ack(_CANCEL))

    answering = asyncio.ensure_future(answer())
    task_reply, report_reply = await asyncio.gather(
        broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=1.0, retries=1),
        broker.send_and_wait(AsyncMock(), "toapp_report_data", send_timeout=1.0, retries=1),
    )
    await answering

    assert task_reply.nav is not None
    assert report_reply.sys is not None
    assert broker._pending == {}  # noqa: SLF001


@pytest.mark.parametrize("how", ["cancel_caller", "close_broker"])
async def test_cancellation_and_close_leave_no_pending_request(how: str) -> None:
    broker = DeviceMessageBroker()
    waiter = asyncio.ensure_future(
        broker.send_and_wait(AsyncMock(), _FIELD, send_timeout=1.0, retries=1, match=lambda _m: True)
    )
    await wait_until(lambda: _FIELD in broker._pending)  # noqa: SLF001
    future = broker._pending[_FIELD].future  # noqa: SLF001

    if how == "cancel_caller":
        waiter.cancel()
    else:
        await broker.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert broker._pending == {}  # noqa: SLF001
    assert future.cancelled()
