"""MowerStateReducer keeps deviceOtherInfo on the device and merges it on field presence."""

from __future__ import annotations

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from tests.unit.device._helpers import make_reducer_device as _make_device


def _other_info_payload(**overrides: object) -> dict[str, object]:
    """Build a minimal deviceOtherInfo dict; every key is optional on the model."""
    base: dict[str, object] = {
        "socCoredump": 2,
        "navCoredump": 1,
        "socTmp": 78,
        "usbDisCnt": 0,
        "vslam_vio": "ok",
    }
    base.update(overrides)
    return base


def test_device_other_info_retained_from_mammotion_push() -> None:
    """The typed deviceOtherInfo snapshot is kept on the device, not discarded."""
    from pymammotion.data.mqtt.mammotion_properties import DeviceOtherInfo, DeviceProperties
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

    reducer = MowerStateReducer()
    device = _make_device()
    assert device.device_other_info.soc_coredump is None

    props = MammotionPropertiesMessage(
        id="1",
        version="1.0",
        sys={},
        params=DeviceProperties(device_other_info=DeviceOtherInfo.from_dict(_other_info_payload())),
    )
    updated = reducer.apply_mammotion_properties(device, props)

    assert updated.device_other_info.soc_coredump == 2
    assert updated.device_other_info.nav_coredump == 1
    assert updated.device_other_info.soc_tmp == 78
    assert updated.device_other_info.vslam_vio == "ok"
    # The input device must not be mutated in place.
    assert device.device_other_info.soc_coredump is None


def test_device_other_info_merges_on_presence_not_truthiness() -> None:
    """A later partial post updates only the keys it carries; a genuine 0 still applies."""
    from pymammotion.data.mqtt.mammotion_properties import DeviceOtherInfo, DeviceProperties
    from pymammotion.data.mqtt.properties import MammotionPropertiesMessage

    reducer = MowerStateReducer()
    device = _make_device()

    def push(dev: MowerDevice, payload: dict[str, object]) -> MowerDevice:
        return reducer.apply_mammotion_properties(
            dev,
            MammotionPropertiesMessage(
                id="1",
                version="1.0",
                sys={},
                params=DeviceProperties(device_other_info=DeviceOtherInfo.from_dict(payload)),
            ),
        )

    device = push(device, _other_info_payload())
    assert device.device_other_info.soc_tmp == 78

    # A post that omits socTmp must leave the established value alone...
    device = push(device, {"socCoredump": 3})
    assert device.device_other_info.soc_coredump == 3
    assert device.device_other_info.soc_tmp == 78
    assert device.device_other_info.nav_coredump == 1

    # ...but a reported 0 is a real value and must be applied.
    device = push(device, {"socTmp": 0})
    assert device.device_other_info.soc_tmp == 0


def test_device_other_info_partial_payload_does_not_raise() -> None:
    """A deviceOtherInfo carrying one key must decode, not MissingField the whole post."""
    from pymammotion.data.mqtt.mammotion_properties import DeviceOtherInfo

    info = DeviceOtherInfo.from_dict({"socCoredump": 1})
    assert info.soc_coredump == 1
    assert info.soc_tmp is None
    assert info.nav is None


def test_device_other_info_retained_from_aliyun_properties() -> None:
    """The Aliyun thing.properties path retains the snapshot as well as mileage/wt_sec."""
    import json as _json
    from types import SimpleNamespace

    from pymammotion.data.mqtt.properties import Item, Items

    reducer = MowerStateReducer()
    device = _make_device()

    payload = _other_info_payload(mileage=1234, wt_sec=5678)
    items = Items(deviceOtherInfo=Item(time=0, value=_json.dumps(payload)))
    # apply_properties only reads properties.params.items.
    msg = SimpleNamespace(params=SimpleNamespace(items=items))
    updated = reducer.apply_properties(device, msg)  # type: ignore[arg-type]

    # Existing behaviour preserved.
    assert updated.report_data.dev.mileage == 1234
    assert updated.report_data.dev.work_time_sec == 5678
    # New: the typed snapshot is retained instead of discarded.
    assert updated.device_other_info.soc_coredump == 2
    assert updated.device_other_info.nav_coredump == 1
    assert updated.device_other_info.vslam_vio == "ok"


def test_yuka_mini2_fixture_device_other_info_fully_modelled() -> None:
    """Every key in a real deviceOtherInfo payload maps to a model field."""
    import dataclasses
    import json as _json
    from pathlib import Path

    from pymammotion.data.mqtt.mammotion_properties import DeviceOtherInfo

    fixture = Path(__file__).parents[2] / "fixtures" / "yuka_mini2_property_post.json"
    raw = _json.loads(_json.loads(fixture.read_text())["params"]["deviceOtherInfo"])

    known: set[str] = set()
    for f in dataclasses.fields(DeviceOtherInfo):
        known.add(f.name)
        for meta in getattr(DeviceOtherInfo.__annotations__[f.name], "__metadata__", ()) or ():
            name = getattr(meta, "name", None)
            if name:
                known.add(name)

    assert [k for k in raw if k not in known] == []

    info = DeviceOtherInfo.from_dict(raw)
    assert info.nav_coredump == 1
    assert info.process_restart_count == -1
    assert info.cur_tilt_degree == "3.68"
