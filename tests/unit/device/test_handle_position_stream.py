"""DeviceHandle position-sample streams and exclusive report-subscription leases."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.device.handle import DeviceHandle
from pymammotion.proto import LubaMsg as RealLubaMsg, RptAct
from pymammotion.transport.base import TransportType
from tests._helpers import make_mock_handle, make_mock_transport


def position_report_message(*, x: int = 12_500, y: int = -8_000, toward: int = 900_000) -> RealLubaMsg:
    """Return a valid report-data position payload."""
    from pymammotion.proto import MctlSys, ReportInfoData, RptDevLocation, RptRtk

    return RealLubaMsg(
        sys=MctlSys(
            toapp_report_data=ReportInfoData(
                locations=[
                    RptDevLocation(
                        real_pos_x=x,
                        real_pos_y=y,
                        real_toward=toward,
                        pos_type=1,
                        zone_hash=123,
                    )
                ],
                rtk=RptRtk(status=4, pos_level=1),
            )
        )
    )


async def test_identical_position_payloads_publish_distinct_immutable_samples() -> None:
    """Fresh payload evidence must not depend on coordinate inequality."""
    from pymammotion.data.model.device import MowerDevice

    handle = DeviceHandle(
        device_id="dev-position",
        device_name="Luba-Position",
        initial_device=MowerDevice(name="Luba-Position"),
    )
    stream = handle.open_position_sample_stream()
    message = position_report_message()

    await handle.on_raw_message(bytes(message), TransportType.BLE)
    first = stream.queue.get_nowait()
    await handle.on_raw_message(bytes(message), TransportType.BLE)
    second = stream.queue.get_nowait()

    assert second.sequence == first.sequence + 1
    assert second.epoch == first.epoch
    assert (second.x, second.y, second.toward) == (1.25, -0.8, 90.0)
    assert second.source == "report_data.locations[0]"
    assert second.transport == TransportType.BLE.value
    assert second.valid_for_motion is True
    assert second.rejection_reason is None
    assert (
        second.received_at_monotonic
        <= second.decoded_at_monotonic
        <= second.broker_completed_at_monotonic
        <= second.reducer_completed_at_monotonic
        <= second.state_applied_at_monotonic
        <= second.published_at_monotonic
    )
    with pytest.raises(FrozenInstanceError):
        second.x = 99.0  # type: ignore[misc]


async def test_non_position_message_publishes_no_position_sample() -> None:
    """Aggregate transport activity must not masquerade as position evidence."""
    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlSys, ReportInfoData, RptDevStatus

    handle = DeviceHandle(
        device_id="dev-generic",
        device_name="Luba-Generic",
        initial_device=MowerDevice(name="Luba-Generic"),
    )
    stream = handle.open_position_sample_stream()

    await handle.on_raw_message(
        bytes(LubaMsg(sys=MctlSys(toapp_report_data=ReportInfoData(dev=RptDevStatus(battery_val=41)))))
    )

    assert stream.queue.empty()
    assert handle.last_report_at > 0


async def test_position_stream_is_latest_wins_and_counts_drops() -> None:
    """A slow consumer gets the newest sample and an explicit gap signal."""
    from pymammotion.data.model.device import MowerDevice

    handle = DeviceHandle(
        device_id="dev-latest",
        device_name="Luba-Latest",
        initial_device=MowerDevice(name="Luba-Latest"),
    )
    stream = handle.open_position_sample_stream(maxsize=1)

    await handle.on_raw_message(bytes(position_report_message(x=10_000)))
    await handle.on_raw_message(bytes(position_report_message(x=20_000)))
    sample = stream.queue.get_nowait()

    assert sample.x == 2.0
    assert sample.sequence == 2
    assert stream.dropped_samples == 1
    assert handle.position_samples_dropped_total == 1


async def test_position_stream_closes_and_transport_replacement_invalidates_queue() -> None:
    """Queued evidence cannot cross a transport epoch or survive close()."""
    from pymammotion.data.model.device import MowerDevice

    original = make_mock_transport(TransportType.BLE)
    replacement = make_mock_transport(TransportType.BLE)
    handle = DeviceHandle(
        device_id="dev-epoch",
        device_name="Luba-Epoch",
        initial_device=MowerDevice(name="Luba-Epoch"),
        ble_transport=original,
    )
    stream = handle.open_position_sample_stream()
    await handle.on_raw_message(bytes(position_report_message()))
    assert not stream.queue.empty()

    await handle.add_transport(replacement)

    assert handle.position_epoch == 1
    assert stream.queue.empty()
    stream.close()
    assert stream.closed is True
    await handle.on_raw_message(bytes(position_report_message(x=30_000)))
    assert stream.queue.empty()


async def test_exclusive_report_subscription_stops_and_restores_background_owner() -> None:
    """An isolated cadence probe cannot race the background renewal loop."""
    from pymammotion.data.model.device import MowerDevice

    handle = DeviceHandle(
        device_id="dev-exclusive-report",
        device_name="Luba-Exclusive-Report",
        initial_device=MowerDevice(name="Luba-Exclusive-Report"),
    )
    handle.ble_stream_active = True
    handle.enqueue_ble_stream_command = AsyncMock()  # type: ignore[method-assign]

    async with handle.exclusive_report_subscription("cadence-probe") as lease:
        assert handle.exclusive_report_subscription_active is True
        assert handle.report_subscription_owner == "cadence-probe"
        assert lease.owner == "cadence-probe"
        # The quiescing STOP is enqueued, never confirmed: the lease reports
        # intent, and only a position payload inside a generation proves the
        # configuration is live.
        assert lease.background_stop_enqueued is True
        assert handle.ble_stream_active is False

        generation = handle.begin_report_subscription_generation(lease)
        assert generation.lease_id == lease.lease_id
        assert generation.generation == 1
        assert generation.baseline_position_sequence == 0
        assert generation.baseline_position_epoch == 0

    handle.enqueue_ble_stream_command.assert_awaited_once_with(  # type: ignore[attr-defined]
        RptAct.RPT_STOP, count=1
    )
    assert handle.exclusive_report_subscription_active is False
    assert handle.report_subscription_owner is None
    with pytest.raises(RuntimeError, match="no longer current"):
        handle.begin_report_subscription_generation(lease)


async def test_report_subscription_leases_are_serialized() -> None:
    """A second report owner waits instead of racing the first owner."""
    handle = make_mock_handle()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def _first() -> None:
        async with handle.exclusive_report_subscription("first"):
            first_entered.set()
            await release_first.wait()

    async def _second() -> None:
        async with handle.exclusive_report_subscription("second"):
            second_entered.set()

    first_task = asyncio.create_task(_first())
    await first_entered.wait()
    second_task = asyncio.create_task(_second())
    await asyncio.sleep(0)
    assert second_entered.is_set() is False
    assert handle.report_subscription_owner == "first"

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_entered.is_set() is True
    assert handle.report_subscription_owner is None


async def test_cancelled_report_subscription_releases_and_rearms_once() -> None:
    """Cancellation cannot strand ownership or duplicate background rearms."""
    handle = make_mock_handle()
    handle._rearm_event = MagicMock()  # type: ignore[assignment]
    entered = asyncio.Event()

    async def _owner() -> None:
        async with handle.exclusive_report_subscription("cancelled"):
            entered.set()
            await asyncio.Future()

    task = asyncio.create_task(_owner())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert handle.exclusive_report_subscription_active is False
    assert handle.report_subscription_owner is None
    handle._rearm_event.set.assert_called_once_with()  # type: ignore[attr-defined]


async def test_rapid_state_position_payload_is_published_after_reduction() -> None:
    """Rapid-state position is a first-class source alongside report locations."""
    from pymammotion.data.model.device import MowerDevice
    from pymammotion.proto import LubaMsg, MctlSys, SystemTardStateTunnelMsg

    handle = DeviceHandle(
        device_id="dev-rapid",
        device_name="Luba-Rapid",
        initial_device=MowerDevice(name="Luba-Rapid"),
    )
    stream = handle.open_position_sample_stream()
    raw = [4, 1, 20, 10_000, 1, 1, 10, 15_000, -4_000, 450_000, 1, 456]

    await handle.on_raw_message(
        bytes(LubaMsg(sys=MctlSys(system_tard_state_tunnel=SystemTardStateTunnelMsg(tard_state_data=raw))))
    )
    sample = stream.queue.get_nowait()

    assert sample.source == "mowing_state"
    assert (sample.x, sample.y, sample.toward) == (1.5, -0.4, 45.0)
    assert sample.rtk_status == 4
    assert sample.valid_for_motion is True
