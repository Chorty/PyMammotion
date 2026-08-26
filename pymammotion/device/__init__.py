"""Device handle and registry for PyMammotion."""

from pymammotion.device.handle import DeviceHandle, DeviceRegistry
from pymammotion.device.position import (
    PositionSample,
    PositionSampleStream,
    ReportSubscriptionGeneration,
    ReportSubscriptionLease,
)
from pymammotion.device.state_reducer import MowerStateReducer, PoolStateReducer, StateReducer, get_state_reducer

__all__ = [
    "DeviceHandle",
    "DeviceRegistry",
    "MowerStateReducer",
    "PoolStateReducer",
    "PositionSample",
    "PositionSampleStream",
    "ReportSubscriptionGeneration",
    "ReportSubscriptionLease",
    "StateReducer",
    "get_state_reducer",
]
