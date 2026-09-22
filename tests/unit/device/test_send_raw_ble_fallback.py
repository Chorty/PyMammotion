"""A failed cloud send retries over a BLE link that is already connected.

The mirror of the BLE->MQTT fallback in ``send_raw``.  It applies to every
``send_raw`` caller uniformly; nothing here is motion-aware or motion-exempt.

``active_transport()`` always selects a *connected* BLE over the cloud, so the
cloud is only the transport actually tried when BLE was not yet connected at
selection time.  The "falls back" tests therefore start BLE disconnected and flip
it to connected inside the failing send, modelling BLE finishing a background
reconnect while the doomed cloud send is in flight.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.aliyun.exceptions import TooManyRequestsException
from pymammotion.device.handle import DeviceHandle
from pymammotion.transport.base import TransportError, TransportRateLimitedError, TransportType
from tests._helpers import make_mock_mowing_device, make_mock_transport


def _make_handle() -> DeviceHandle:
    return DeviceHandle(device_id="dev1", device_name="Luba-Fallback", initial_device=make_mock_mowing_device())


def _make_ble_transport(*, connected: bool = True) -> MagicMock:
    """A BLE transport that is usable exactly when connected, so send_raw never schedules a reconnect."""
    ble = MagicMock()
    ble.transport_type = TransportType.BLE
    ble.is_connected = connected
    ble.is_usable = connected
    ble.is_rate_limited = False
    ble.send = AsyncMock()
    ble.disconnect = AsyncMock()
    ble.on_message = None
    ble.last_received_monotonic = 0.0
    ble.last_send_monotonic = 0.0
    return ble


def _wire(handle: DeviceHandle, mqtt: MagicMock, ble: MagicMock | None) -> None:
    handle._transports[TransportType.CLOUD_ALIYUN] = mqtt  # noqa: SLF001
    if ble is not None:
        handle._transports[TransportType.BLE] = ble  # noqa: SLF001


def _fail_first_then_connect(ble: MagicMock, error: Exception) -> AsyncMock:
    calls = 0

    async def _send_marked(transport: object, payload: bytes, **_: Any) -> None:  # noqa: ARG001
        nonlocal calls
        calls += 1
        if calls == 1:
            ble.is_connected = True  # BLE finishes reconnecting mid-send
            raise error

    return AsyncMock(side_effect=_send_marked)


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(TransportRateLimitedError("blocked"), id="rate-limit-pre-check"),
        pytest.param(TransportError("cloud publish failed"), id="generic-transport-error"),
        pytest.param(TooManyRequestsException("rate limited", "iot-id"), id="cloud-429"),
    ],
)
async def test_send_raw_falls_back_to_connected_ble(error: Exception) -> None:
    """Each cloud failure retries once over BLE, and the retry is what the caller sees."""
    handle = _make_handle()
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_ble_transport(connected=False)
    _wire(handle, mqtt, ble)
    handle._send_marked = _fail_first_then_connect(ble, error)  # type: ignore[method-assign]

    await handle.send_raw(b"\x01", user_initiated=True)

    calls = handle._send_marked.await_args_list  # type: ignore[attr-defined]
    assert [c.args[0] for c in calls] == [mqtt, ble]
    # A person is waiting whichever transport carries it.
    assert calls[1].kwargs["user_initiated"] is True


async def test_cloud_429_arms_the_ban_even_when_ble_carries_the_payload() -> None:
    """The 429 is real cloud state, not a routing decision."""
    handle = _make_handle()
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    ble = _make_ble_transport(connected=False)
    _wire(handle, mqtt, ble)
    handle._send_marked = _fail_first_then_connect(ble, TooManyRequestsException("rate limited", "iot-id"))  # type: ignore[method-assign]

    await handle.send_raw(b"\x00")

    mqtt.set_rate_limited.assert_called_once()


async def test_no_fallback_when_ble_stays_disconnected() -> None:
    """A BLE that never connects is not used, and the refusal still reaches the caller."""
    handle = _make_handle()
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.send = AsyncMock(side_effect=TooManyRequestsException("rate limited", "iot-id"))
    ble = _make_ble_transport(connected=False)
    _wire(handle, mqtt, ble)

    with pytest.raises(TooManyRequestsException):
        await handle.send_raw(b"\x00")

    ble.send.assert_not_awaited()
    mqtt.set_rate_limited.assert_called_once()


async def test_rate_limited_send_with_no_ble_still_raises() -> None:
    """With no BLE transport at all, upstream's contract holds: a blocked send raises."""
    handle = _make_handle()
    mqtt = make_mock_transport(TransportType.CLOUD_ALIYUN)
    mqtt.is_send_blocked = MagicMock(return_value=True)
    _wire(handle, mqtt, None)

    with pytest.raises(TransportRateLimitedError):
        await handle.send_raw(b"\x01")

    mqtt.send.assert_not_awaited()


def test_connected_ble_fallback_is_none_when_ble_was_the_failed_transport() -> None:
    """There is nothing to mirror onto when BLE itself failed."""
    handle = _make_handle()
    handle._transports[TransportType.BLE] = _make_ble_transport(connected=True)  # noqa: SLF001

    assert handle._connected_ble_fallback(TransportType.BLE) is None  # noqa: SLF001
