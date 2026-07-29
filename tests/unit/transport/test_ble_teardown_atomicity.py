"""BLETransport must release every live client it established, whatever fails.

A client dropped without a ``disconnect()`` keeps its proxy/adapter connection slot,
so each leak shrinks the pool until no connection can be made at all.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BLEDevice
import pytest

from pymammotion.transport.base import BLEUnavailableError, TransportError
from pymammotion.transport.ble import BLETransport, BLETransportConfig
from tests.unit.transport._fakes import make_ble_device, make_fake_ble_client, make_fake_ble_message


class TimeoutAPIError(TimeoutError):
    """Stand-in for a BLE proxy API timeout raised outside bleak."""


@pytest.fixture
def config() -> BLETransportConfig:
    """Transport config with room for several failures before the cooldown trips."""
    return BLETransportConfig(device_id="test-device-001", ble_address="AA:BB:CC:DD:EE:FF", connect_failure_threshold=3)


def _transport(config: BLETransportConfig) -> BLETransport:
    transport = BLETransport(config)
    transport.set_ble_device(make_ble_device("AA:BB:CC:DD:EE:FF"))
    return transport


async def test_disconnect_attempts_teardown_when_client_reports_disconnected(config: BLETransportConfig) -> None:
    """A false is_connected value must not suppress backend resource cleanup."""
    transport = BLETransport(config)
    fake_client = make_fake_ble_client(connected=False)
    transport._client = fake_client  # noqa: SLF001

    await transport.disconnect()

    fake_client.disconnect.assert_awaited_once()
    assert transport._client is None  # noqa: SLF001


async def test_send_timeout_disconnects_live_client_before_dropping_reference(config: BLETransportConfig) -> None:
    """A timed-out write must release its live client before clearing it."""
    transport = BLETransport(config)
    transport.set_ble_device(MagicMock(spec=BLEDevice))
    fake_client = make_fake_ble_client()
    fake_msg = make_fake_ble_message()

    async def _disconnect() -> None:
        assert transport._client is fake_client  # noqa: SLF001
        fake_client.is_connected = False

    fake_client.disconnect.side_effect = _disconnect

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble.BleMessage", return_value=fake_msg),
    ):
        await transport.connect()
        fake_msg.post_custom_data_bytes.reset_mock()
        fake_msg.post_custom_data_bytes.side_effect = TimeoutError("write timed out")

        with pytest.raises(TransportError, match="write timed out"):
            await transport.send(b"\xde\xad\xbe\xef")

    fake_client.disconnect.assert_awaited_once()
    assert transport._client is None  # noqa: SLF001


async def test_start_notify_timeout_releases_client_and_chains_original(config: BLETransportConfig) -> None:
    """A timeout is wrapped for the MQTT fallback, keeps its cause, and still disconnects."""
    transport = _transport(config)
    fake_client = make_fake_ble_client()
    original = TimeoutAPIError("notify timed out")
    fake_client.start_notify.side_effect = original

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        pytest.raises(BLEUnavailableError, match="notify timed out") as raised,
    ):
        await transport.connect()

    assert raised.value.__cause__ is original
    fake_client.disconnect.assert_awaited_once()
    assert transport._client is None  # noqa: SLF001
    assert transport._message is None  # noqa: SLF001


async def test_start_notify_unexpected_error_releases_client_and_escapes_unchanged(config: BLETransportConfig) -> None:
    """An error outside the anticipated transport set must disconnect and propagate as-is."""
    transport = _transport(config)
    fake_client = make_fake_ble_client()
    original = RuntimeError("proxy failed")
    fake_client.start_notify.side_effect = original

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        pytest.raises(RuntimeError, match="proxy failed") as raised,
    ):
        await transport.connect()

    assert raised.value is original
    fake_client.disconnect.assert_awaited_once()
    assert transport._client is None  # noqa: SLF001
    assert transport._message is None  # noqa: SLF001


async def test_start_notify_cancellation_releases_client_and_propagates(config: BLETransportConfig) -> None:
    """Cancellation during post-connect setup must not leak the live client."""
    transport = _transport(config)
    fake_client = make_fake_ble_client()
    fake_client.start_notify.side_effect = asyncio.CancelledError

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        pytest.raises(asyncio.CancelledError),
    ):
        await transport.connect()

    fake_client.disconnect.assert_awaited_once()
    assert transport._client is None  # noqa: SLF001
    assert transport._message is None  # noqa: SLF001


async def test_setup_cleanup_failure_does_not_replace_original_exception(config: BLETransportConfig) -> None:
    """A teardown error must not mask the setup failure that triggered it."""
    transport = _transport(config)
    fake_client = make_fake_ble_client()
    original = RuntimeError("notify failed")
    fake_client.start_notify.side_effect = original
    fake_client.disconnect.side_effect = RuntimeError("cleanup failed")

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        pytest.raises(RuntimeError, match="notify failed") as raised,
    ):
        await transport.connect()

    assert raised.value is original
    fake_client.disconnect.assert_awaited_once()


async def test_hung_teardown_is_time_bounded(config: BLETransportConfig) -> None:
    """A disconnect that never returns must not hang the failure path."""
    transport = _transport(config)
    fake_client = make_fake_ble_client()
    fake_client.start_notify.side_effect = RuntimeError("notify failed")

    async def _hang() -> None:
        await asyncio.Event().wait()

    fake_client.disconnect.side_effect = _hang

    with (
        patch("pymammotion.transport.ble.establish_connection", new=AsyncMock(return_value=fake_client)),
        patch("pymammotion.transport.ble._DISCONNECT_TIMEOUT_SECONDS", 0.01),
        pytest.raises(RuntimeError, match="notify failed"),
    ):
        await asyncio.wait_for(transport.connect(), timeout=2.0)

    assert transport._client is None  # noqa: SLF001


async def test_repeated_setup_failures_balance_connections_and_disconnects(config: BLETransportConfig) -> None:
    """Every established client must be disconnected across repeated setup failures."""
    attempts = 3
    transport = _transport(replace(config, connect_failure_threshold=attempts + 1))
    clients = [make_fake_ble_client() for _ in range(attempts)]
    for client in clients:
        client.start_notify.side_effect = TimeoutError("notify timed out")

    establish = AsyncMock(side_effect=clients)
    with patch("pymammotion.transport.ble.establish_connection", new=establish):
        for _ in range(attempts):
            with pytest.raises(BLEUnavailableError, match="notify timed out"):
                await transport.connect()

    assert establish.await_count == attempts
    assert all(client.disconnect.await_count == 1 for client in clients)
