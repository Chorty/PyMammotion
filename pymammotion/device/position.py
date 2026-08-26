"""Immutable position evidence published by :class:`DeviceHandle`."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class PositionSample:
    """One reduced mower-position payload with monotonic pipeline timing."""

    sequence: int
    epoch: int
    x: float | None
    y: float | None
    toward: float | None
    pos_type: int | None
    zone_hash: int | None
    rtk_status: int | None
    pos_level: int | None
    source: str
    transport: str
    received_at_monotonic: float
    decoded_at_monotonic: float
    broker_completed_at_monotonic: float
    reducer_completed_at_monotonic: float
    state_applied_at_monotonic: float
    published_at_monotonic: float
    valid_for_motion: bool
    rejection_reason: str | None


class PositionSampleStream:
    """A bounded, latest-wins queue of immutable position samples."""

    def __init__(
        self,
        *,
        maxsize: int,
        unsubscribe: Callable[[PositionSampleStream], None],
    ) -> None:
        """Create a stream whose queue never grows without bound."""
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self.queue: asyncio.Queue[PositionSample] = asyncio.Queue(maxsize=maxsize)
        self._unsubscribe = unsubscribe
        self._closed = False
        self._dropped_samples = 0

    @property
    def closed(self) -> bool:
        """Return whether this stream no longer accepts samples."""
        return self._closed

    @property
    def dropped_samples(self) -> int:
        """Return how many queued samples latest-wins delivery replaced."""
        return self._dropped_samples

    def _offer(self, sample: PositionSample) -> bool:
        """Offer *sample* without blocking; return true when one was dropped."""
        if self._closed:
            return False
        dropped = False
        if self.queue.full():
            self.queue.get_nowait()
            self._dropped_samples += 1
            dropped = True
        self.queue.put_nowait(sample)
        return dropped

    def _invalidate(self) -> None:
        """Discard evidence queued before a connection-epoch transition."""
        while not self.queue.empty():
            self.queue.get_nowait()

    def close(self) -> None:
        """Unsubscribe and discard queued evidence."""
        if self._closed:
            return
        self._closed = True
        self._invalidate()
        self._unsubscribe(self)

    cancel = close

    def __enter__(self) -> Self:
        """Return this stream for synchronous context-manager use."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Close this stream on context-manager exit."""
        self.close()


@dataclass(frozen=True, slots=True)
class ReportSubscriptionLease:
    """Exclusive ownership of one device's report-subscription configuration.

    ``background_stop_enqueued_at_monotonic`` is when the quiescing ``RPT_STOP``
    was placed on the device command queue -- NOT when the device acknowledged
    it, and NOT proof that background reporting has stopped.
    ``DeviceCommandQueue.enqueue`` returns as soon as the item is queued, a
    ``BACKGROUND`` item is dropped outright while a saga is active, and the send
    is skipped when no BLE transport is connected.  Treat this field as evidence
    of intent; the only positive evidence that a configuration is live is a
    position payload inside a :class:`ReportSubscriptionGeneration`.
    """

    owner: str
    lease_id: int
    acquired_at_monotonic: float
    background_stop_enqueued: bool
    background_stop_enqueued_at_monotonic: float


@dataclass(frozen=True, slots=True)
class ReportSubscriptionGeneration:
    """Evidence boundary for one report configuration within an active lease."""

    owner: str
    lease_id: int
    generation: int
    requested_at_monotonic: float
    baseline_position_sequence: int
    baseline_position_epoch: int
    baseline_last_report_at: float
