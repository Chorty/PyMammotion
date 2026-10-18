"""Share-notice parsing: missing display metadata must not take the Aliyun login down.

The real cloud omits ``initiatorAlias`` on some share records (seen on accepted and
expired shares).  A required ``initiator_alias`` made one such record fail the whole
``getShareNoticeList`` parse, which ``_connect_aliyun_for_login`` turned into "Aliyun
setup failed — continuing without the Aliyun transport", dropping every Aliyun-only
device (the RTK base) even though authentication and the device listing had succeeded.

All values below are synthetic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from mashumaro.exceptions import InvalidFieldValue, MissingField
import orjson
import pytest

from pymammotion.aliyun.exceptions import CloudSetupError
from pymammotion.aliyun.model.aep_response import AepResponse
from pymammotion.aliyun.model.dev_by_account_response import ShareNoticeListResponse, ShareNotification
from pymammotion.client_auth import CloudAuthMixin
from tests.unit.aliyun._helpers import make_gateway

_UNSET = object()


def _record(*, status: int = 0, record_id: str = "record-1", initiator_alias: Any = _UNSET) -> dict[str, Any]:
    """Build a share record with every field the model requires, plus optional display metadata."""
    record: dict[str, Any] = {
        "gmtModified": 1_700_000_000_000,
        "targetId": "target-1",
        "targetType": "DEVICE",
        "gmtCreate": 1_700_000_000_000,
        "batchId": "batch-1",
        "nodeType": "DEVICE",
        "deviceName": "RTK-SYNTHETIC",
        "productName": "ReferenceStation",
        "recordId": record_id,
        "initiatorIdentityId": "initiator-1",
        "isReceiver": 1,
        "status": status,
        "receiverIdentityId": "receiver-1",
        "receiverAlias": "receiver-alias",
    }
    if initiator_alias is not _UNSET:
        record["initiatorAlias"] = initiator_alias
    return record


def _notice_list(*records: dict[str, Any], code: int = 200) -> dict[str, Any]:
    return {
        "code": code,
        "id": "request-1",
        "data": {"total": len(records), "data": list(records), "pageNo": 1, "pageSize": 100},
    }


# --- model ---------------------------------------------------------------------------


def test_missing_initiator_alias_deserializes_as_none() -> None:
    notice = ShareNotification.from_dict(_record())

    assert notice.initiator_alias is None
    assert notice.record_id == "record-1"
    assert notice.status == 0


def test_present_initiator_alias_is_kept() -> None:
    notice = ShareNotification.from_dict(_record(initiator_alias="initiator-alias"))

    assert notice.initiator_alias == "initiator-alias"


def test_null_initiator_alias_deserializes_as_none() -> None:
    notice = ShareNotification.from_dict(_record(initiator_alias=None))

    assert notice.initiator_alias is None


def test_missing_required_field_still_fails() -> None:
    """Only the display alias became optional: a record without its id is still invalid."""
    record = _record()
    del record["recordId"]

    with pytest.raises(MissingField, match="record_id"):
        ShareNotification.from_dict(record)


def test_mixed_list_keeps_every_record() -> None:
    """The live shape: some records carry the alias, some do not; none may be dropped."""
    response = ShareNoticeListResponse.from_dict(
        _notice_list(
            _record(record_id="record-1", initiator_alias="initiator-alias"),
            _record(record_id="record-2"),
            _record(record_id="record-3", status=3),
        )
    )

    assert response.data is not None
    assert [n.record_id for n in response.data.data] == ["record-1", "record-2", "record-3"]
    assert [n.initiator_alias for n in response.data.data] == ["initiator-alias", None, None]


# --- gateway -------------------------------------------------------------------------


async def _fetch_notices(body: dict[str, Any]) -> ShareNoticeListResponse:
    mock_response = MagicMock()
    mock_response.body = orjson.dumps(body)
    mock_client = MagicMock()
    mock_client.async_do_request = AsyncMock(return_value=mock_response)
    with patch("pymammotion.aliyun.cloud_gateway.Client", return_value=mock_client):
        return await make_gateway().get_shared_notice_list()


async def test_gateway_parses_notice_list_without_initiator_alias() -> None:
    response = await _fetch_notices(_notice_list(_record(), _record(record_id="record-2", status=3)))

    assert response.data is not None
    assert [n.record_id for n in response.data.data] == ["record-1", "record-2"]


async def test_gateway_still_raises_on_rejected_request() -> None:
    """A non-200 reply (e.g. a rejected token) must keep failing loudly, not parse as empty."""
    with pytest.raises(CloudSetupError, match="shared notice list"):
        await _fetch_notices({"code": 401, "id": "request-1", "msg": "request auth error."})


async def test_gateway_still_raises_on_malformed_record() -> None:
    record = _record()
    del record["recordId"]

    with pytest.raises(InvalidFieldValue):
        await _fetch_notices(_notice_list(record))


# --- login path ----------------------------------------------------------------------


async def test_login_keeps_aliyun_client_when_alias_missing() -> None:
    """The failing step of the 2026-10-18 login: the gateway is returned and pending shares accepted."""
    gateway = make_gateway()
    gateway._aep_response = MagicMock(spec=AepResponse)  # noqa: SLF001 — normally set by _connect_iot
    gateway.confirm_share = AsyncMock(return_value=True)  # type: ignore[method-assign]
    auth = MagicMock()
    auth._connect_iot = AsyncMock()  # noqa: SLF001

    body = _notice_list(
        _record(record_id="accepted", status=0),
        _record(record_id="pending", status=-1),
        _record(record_id="expired", status=3, initiator_alias="initiator-alias"),
    )
    mock_response = MagicMock()
    mock_response.body = orjson.dumps(body)
    mock_client = MagicMock()
    mock_client.async_do_request = AsyncMock(return_value=mock_response)

    with (
        patch("pymammotion.client_auth.CloudIOTGateway", return_value=gateway),
        patch("pymammotion.aliyun.cloud_gateway.Client", return_value=mock_client),
    ):
        result = await CloudAuthMixin._connect_aliyun_for_login(auth, MagicMock())  # noqa: SLF001

    assert result is gateway
    auth._connect_iot.assert_awaited_once_with(gateway)  # noqa: SLF001
    gateway.confirm_share.assert_awaited_once_with(["pending"])
