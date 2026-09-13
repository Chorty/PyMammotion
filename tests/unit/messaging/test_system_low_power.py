"""Wire-format pins for the read-only low-power GET builder."""

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
