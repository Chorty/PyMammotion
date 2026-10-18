"""Per-command reply identity, result validation and replay policy for send_and_wait.

The broker correlates a reply by its protobuf oneof field alone, and the Mammotion
protocol carries no request ID or sequence on these replies.  Two consequences:

* A reply on the same field from a different command (a ``cancel_job`` ack while a
  ``pause_execute_task`` is pending) would complete the wrong request.  Where the
  reply echoes enough of the request to tell them apart, a matcher narrows it.
* A late reply to a timed-out attempt is indistinguishable from the reply to its
  resend.  For a read that is harmless; for an action, the resend itself may change
  physical state a second time.  Those commands are sent exactly once.

Two identical requests on the same field remain ambiguous: a delayed reply to the
first can still complete the second.  Nothing here can tell them apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import betterproto2

from pymammotion.proto import LubaMsg

if TYPE_CHECKING:
    from collections.abc import Callable

#: Attempts for a command not listed below — the broker's historical default.
DEFAULT_ATTEMPTS: Final = 2

#: ``MammotionCommand`` builders whose single delivery can change physical state:
#: task control, undock/dock, job start/plan, blades and movement.  An ambiguous
#: send or reply timeout must not resend them; the caller learns the outcome is
#: unconfirmed instead.
NO_REPLAY_COMMANDS: Final = frozenset(
    {
        "break_point_anywhere_continue",
        "break_point_continue",
        "cancel_job",
        "cancel_return_to_dock",
        "continue_last_job",
        "end_draw_corridor",
        "fast_aotu_test",
        "generate_route_information",
        "leave_dock",
        "modify_route_information",
        "move_back",
        "move_forward",
        "move_left",
        "move_right",
        "operate_on_device",
        "pause_execute_task",
        "re_charge_test",
        "reset_base_station",
        "resume_execute_task",
        "return_to_dock",
        "send_movement",
        "set_blade_control",
        "start_job",
        "start_mapless_mow",
        "start_no_area_work",
        "stop_and_not_save_task",
    }
)

_TASK_CTRL_ACK: Final = "todev_taskctrl_ack"


@dataclass(frozen=True, slots=True)
class ReplyContract:
    """How one ``send_command_and_wait`` call is correlated, validated and retried."""

    attempts: int
    match: Callable[[Any], bool] | None = None
    result: Callable[[Any], int] | None = None


def _sent_task_ctrl(command_bytes: bytes) -> tuple[int, int] | None:
    """Return the ``(type, action)`` of an outgoing ``nav.todev_taskctrl``, if it is one."""
    group, body = betterproto2.which_one_of(LubaMsg().parse(command_bytes), "LubaSubMsg")
    if group != "nav" or body is None:
        return None
    field, value = betterproto2.which_one_of(body, "SubNavMsg")
    if field != "todev_taskctrl" or value is None:
        return None
    return value.type, value.action


def _task_ctrl_ack(message: Any) -> Any:
    nav = getattr(message, "nav", None)
    return getattr(nav, _TASK_CTRL_ACK, None)


def contract_for(key: str, expected_field: str, command_bytes: bytes) -> ReplyContract:
    """Return the reply contract for sending *key* and waiting on *expected_field*.

    A ``nav.todev_taskctrl`` waiting on its ack must be answered with the same task
    type and action, and a nonzero ``result`` is the device's refusal.  Commands in
    :data:`NO_REPLAY_COMMANDS` are sent once.  Everything else keeps the historical
    field-only match and :data:`DEFAULT_ATTEMPTS`.
    """
    attempts = 1 if key in NO_REPLAY_COMMANDS else DEFAULT_ATTEMPTS
    if expected_field != _TASK_CTRL_ACK:
        return ReplyContract(attempts=attempts)
    sent = _sent_task_ctrl(command_bytes)
    if sent is None:
        # e.g. leave_dock (todev_one_touch_leave_pile): the ack's action for it is
        # not established, so only the field is matched.
        return ReplyContract(attempts=attempts)
    task_type, action = sent

    def match(message: Any) -> bool:
        ack = _task_ctrl_ack(message)
        return ack is not None and ack.type == task_type and ack.action == action

    def result(message: Any) -> int:
        return int(_task_ctrl_ack(message).result)

    return ReplyContract(attempts=1, match=match, result=result)
