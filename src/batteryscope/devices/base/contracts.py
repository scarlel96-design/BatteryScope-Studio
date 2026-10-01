"""Device contracts. External plugins receive these contracts, not Core internals."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from batteryscope.core.errors import ProtocolError
from batteryscope.core.models import (
    DeviceCapabilities,
    DeviceIdentity,
    MeasurementSample,
)
from batteryscope.safety.stop import StopResult


class IDevice(Protocol):
    @classmethod
    def discover(cls) -> list[DeviceIdentity]: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def get_identity(self) -> DeviceIdentity: ...

    def get_capabilities(self) -> DeviceCapabilities: ...

    def get_status(self) -> str: ...

    def self_test(self) -> bool: ...


class IMeter(IDevice, Protocol):
    def samples(self, count: int) -> Iterable[MeasurementSample]: ...


class ISafetyControllable(Protocol):
    def emergency_stop(self) -> StopResult: ...


class ILoad(IDevice, ISafetyControllable, Protocol):
    def set_constant_current(self, current_a: float) -> None: ...

    def set_constant_power(self, power_w: float) -> None: ...

    def load_on(self) -> None: ...

    def load_off(self) -> None: ...


class IPDAnalyzer(IDevice, Protocol):
    def scan_pdo(self) -> object: ...


class ITemperatureSensor(IDevice, Protocol):
    def read_temperature_c(self) -> float: ...


class IReplayDevice(IMeter, Protocol):
    def provenance(self) -> str: ...


class NotVerifiedProtocolError(ProtocolError):
    """A physical command is blocked until protocol evidence exists."""
