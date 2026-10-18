"""Report-subscription STOP bodies sent by the public ``request_iot_sync*`` entry points.

Every captured ``send_command_with_args`` call is resolved through ``MammotionCommand`` and
the bytes decoded, so the tests check the ``ReportInfoCfg`` the device would receive rather
than the keyword arguments a caller happened to pass.  Configs are compared decoded: the
envelope around them carries a per-message sequence number.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from pymammotion.client import _CONTINUOUS_STREAM_CHANNELS, _ONE_SHOT_CHANNELS, MammotionClient
from pymammotion.homeassistant.mower_api import HomeAssistantMowerApi
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import LubaMsg, ReportInfoCfg, RptAct
from tests._helpers import make_bare_client

_DEVICE = "Luba-VSRPT001"


def _client() -> tuple[MammotionClient, AsyncMock]:
    client = make_bare_client()
    send = AsyncMock()
    client.send_command_with_args = send  # type: ignore[method-assign]
    return client, send


def _payloads(send: AsyncMock) -> list[bytes]:
    """Build the bytes of every captured call; underscore kwargs are send options, not builder args."""
    payloads = []
    for call in send.await_args_list:
        name, command = call.args
        builder_kwargs: dict[str, Any] = {k: v for k, v in call.kwargs.items() if not k.startswith("_")}
        payloads.append(getattr(MammotionCommand(name, user_account=42), command)(**builder_kwargs))
    return payloads


def _cfg(payload: bytes) -> ReportInfoCfg:
    cfg = LubaMsg().parse(payload).sys.todev_report_cfg
    assert cfg is not None, "the payload is not a request_iot_sys report config"
    return cfg


async def _explicit_stop_cfg() -> ReportInfoCfg:
    client, send = _client()
    await client.request_iot_sync_continuous_stop(_DEVICE)
    (payload,) = _payloads(send)
    return _cfg(payload)


@pytest.mark.regression
async def test_continuous_stop_flag_sends_the_count_one_stop() -> None:
    """``request_iot_sync_continuous(stop=True)`` sent RPT_STOP with count=0.

    A count=0 stop was observed not to end the periodic stream, while the explicit
    helper's count=1 body did, so the two public stops disagreed on the wire.
    """
    client, send = _client()

    await client.request_iot_sync_continuous(_DEVICE, stop=True)

    (payload,) = _payloads(send)
    cfg = _cfg(payload)
    assert (cfg.act, cfg.count, list(cfg.sub)) == (RptAct.RPT_STOP, 1, _CONTINUOUS_STREAM_CHANNELS)
    assert cfg == await _explicit_stop_cfg()
    assert send.await_args.kwargs["_record_cmd"] is False


async def test_continuous_stop_ignores_start_timing_arguments() -> None:
    """``period``/``no_change_period`` configure a START; a stop sends the helper's body unchanged."""
    client, send = _client()

    await client.request_iot_sync_continuous(_DEVICE, stop=True, period=250, no_change_period=9000)

    (payload,) = _payloads(send)
    assert _cfg(payload) == await _explicit_stop_cfg()


async def test_explicit_stop_helper_body() -> None:
    cfg = await _explicit_stop_cfg()

    assert (cfg.act, cfg.count, list(cfg.sub)) == (RptAct.RPT_STOP, 1, _CONTINUOUS_STREAM_CHANNELS)
    assert (cfg.timeout, cfg.period, cfg.no_change_period) == (10000, 1000, 1000)


async def test_continuous_start_body_and_defaults_unchanged() -> None:
    client, send = _client()

    await client.request_iot_sync_continuous(_DEVICE)
    await client.request_iot_sync_continuous(_DEVICE, period=250, no_change_period=9000)

    default, custom = (_cfg(p) for p in _payloads(send))
    assert (default.act, default.count, list(default.sub)) == (RptAct.RPT_START, 0, _CONTINUOUS_STREAM_CHANNELS)
    assert (default.timeout, default.period, default.no_change_period) == (10000, 1000, 4000)
    assert (custom.act, custom.count, custom.period, custom.no_change_period) == (RptAct.RPT_START, 0, 250, 9000)
    assert all(call.kwargs["_record_cmd"] is False for call in send.await_args_list)


async def test_one_shot_sync_stop_and_start_are_count_one() -> None:
    """The one-shot entry point already sent count=1 for both actions; pinned, not changed."""
    client, send = _client()

    await client.request_iot_sync(_DEVICE)
    await client.request_iot_sync(_DEVICE, stop=True)

    start, stop = (_cfg(p) for p in _payloads(send))
    assert (start.act, start.count, list(start.sub)) == (RptAct.RPT_START, 1, _ONE_SHOT_CHANNELS)
    assert (stop.act, stop.count, list(stop.sub)) == (RptAct.RPT_STOP, 1, _ONE_SHOT_CHANNELS)


@pytest.mark.regression
@pytest.mark.parametrize(("stop", "act", "count"), [(True, RptAct.RPT_STOP, 1), (False, RptAct.RPT_START, 0)])
async def test_mower_api_request_iot_sync_reaches_the_client_body(stop: bool, act: RptAct, count: int) -> None:
    """The HA facade's ``async_request_iot_sync(stop=True)`` inherited the count=0 stop."""
    client, send = _client()
    api = HomeAssistantMowerApi.__new__(HomeAssistantMowerApi)
    api._mammotion = client

    await api.async_request_iot_sync(_DEVICE, stop=stop)

    (payload,) = _payloads(send)
    cfg = _cfg(payload)
    assert (send.await_args.args[0], cfg.act, cfg.count) == (_DEVICE, act, count)
