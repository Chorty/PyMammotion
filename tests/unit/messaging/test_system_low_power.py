"""Wire-format pins for the read-only low-power GET builder."""

from pymammotion.data.model.device import MowerDevice
from pymammotion.device.state_reducer import MowerStateReducer
from pymammotion.mammotion.commands.mammotion_command import MammotionCommand
from pymammotion.proto import DevLowPowerGet, LubaMsg, MctlSys, MsgCmdType


def test_get_device_low_power_sends_the_oneof_with_presence() -> None:
    """The request must carry to_get_dev_low_power_cmd even though it is empty."""
    raw = MammotionCommand("Luba-VSPLV397", 1).get_device_low_power()
    msg = LubaMsg.parse(raw)
    assert msg.msgtype == MsgCmdType.EMBED_SYS
    assert msg.sys is not None
    assert msg.sys.to_get_dev_low_power_cmd is not None
    assert bytes(msg.sys) == bytes.fromhex("820500")


def test_app_on_dock_and_off_dock_gets_are_byte_identical() -> None:
    """The vendor app's two GETs differ only in a zero field, which proto3 drops."""
    empty = bytes(MctlSys(to_get_dev_low_power_cmd=DevLowPowerGet()))
    on_dock = bytes(MctlSys(to_get_dev_low_power_cmd=DevLowPowerGet(charging_low_power=0)))
    off_dock = bytes(MctlSys(to_get_dev_low_power_cmd=DevLowPowerGet(uncharging_low_power=0)))
    assert empty == on_dock == off_dock == bytes.fromhex("820500")


def test_low_power_switches_are_unknown_until_a_reply_arrives() -> None:
    """None means never received, not off."""
    device = MowerDevice(name="Luba-VSPLV397")
    assert device.mower_state.charging_low_power is None
    assert device.mower_state.uncharging_low_power is None


def test_low_power_reply_is_captured_into_mower_state() -> None:
    """The reducer stores both switches from the reply."""
    reply = LubaMsg(sys=MctlSys(to_get_dev_low_power_cmd=DevLowPowerGet(charging_low_power=1, uncharging_low_power=0)))
    result = MowerStateReducer().apply(MowerDevice(name="Luba-VSPLV397"), reply)
    assert result.mower_state.charging_low_power == 1
    assert result.mower_state.uncharging_low_power == 0


def test_low_power_reply_does_not_mutate_the_previous_snapshot() -> None:
    """The reducer copies mower_state before writing, like the other sys handlers."""
    before = MowerDevice(name="Luba-VSPLV397")
    reply = LubaMsg(sys=MctlSys(to_get_dev_low_power_cmd=DevLowPowerGet(charging_low_power=1)))
    MowerStateReducer().apply(before, reply)
    assert before.mower_state.charging_low_power is None
