"""Deterministic safety gate and priority-ordered emergency stop."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from batteryscope.core.errors import SafetyError
from batteryscope.core.events import Event, EventBus
from batteryscope.core.models import (
    DeviceCapabilities,
    LimitSourceKind,
    SourceKind,
    VerificationStatus,
)
from batteryscope.devices.base.contracts import ISafetyControllable
from batteryscope.safety.stop import StopPhase, StopResult


class SafetyDenied(SafetyError):
    pass


@dataclass(frozen=True)
class LoadRequest:
    mode: str
    current_a: float = 0.0
    power_w: float = 0.0
    voltage_v: float = 0.0
    automatic: bool = True


class SafetyEngine:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.last_stop: StopResult | None = None
        self.pending_events: list[Event] = []
        self.event_dispatch_errors: list[Exception] = []

    def validate_device_limits(self, caps: DeviceCapabilities, kind: SourceKind) -> None:
        if kind == SourceKind.SIMULATED:
            for name in ("max_voltage", "max_current", "max_power"):
                limit = getattr(caps, name)
                if limit.verification_status != VerificationStatus.SIMULATED or limit.source_kind != LimitSourceKind.TEST_FIXTURE:
                    raise SafetyDenied(f"{name} lacks simulated fixture provenance")
            return
        if kind != SourceKind.REAL:
            raise SafetyDenied("replay cannot control a physical load")
        for name in ("max_voltage", "max_current", "max_power"):
            limit = getattr(caps, name)
            if limit.verification_status != VerificationStatus.VERIFIED or limit.source_kind != LimitSourceKind.PHYSICAL_DOCUMENT:
                raise SafetyDenied(f"{name} is not VERIFIED from physical documentation")

    def validate_requested_load(self, request: LoadRequest, caps: DeviceCapabilities, kind: SourceKind) -> None:
        if request.mode not in ("CC", "CP"):
            raise SafetyDenied("unsupported load mode")
        if any(not isfinite(x) or x < 0 for x in (request.current_a, request.power_w, request.voltage_v)):
            raise SafetyDenied("invalid load request")
        feature = "load.constant_current" if request.mode == "CC" else "load.constant_power"
        if not caps.supports(feature):
            raise SafetyDenied(f"missing capability {feature}")
        self.validate_device_limits(caps, kind)
        for actual, limit in ((request.voltage_v, caps.max_voltage), (request.current_a, caps.max_current),
                              (request.power_w, caps.max_power)):
            if limit.value is None or actual > limit.value:
                raise SafetyDenied("requested load exceeds or lacks device limit")

    def validate_device_state(self, connected: bool, status: str) -> None:
        if not connected or status not in ("IDLE", "LOAD_OFF", "CC", "CP"):
            raise SafetyDenied("device is not in a controllable state")

    def _stop(self, control: ISafetyControllable, device_id: str, event_name: str) -> StopResult:
        # No bus, logger, SQL, or disk call may precede the load-off request.
        self.last_stop = StopResult(StopPhase.REQUESTED)
        try:
            result = control.emergency_stop()
            if not isinstance(result, StopResult):
                result = StopResult(StopPhase.ACKNOWLEDGED, detail="driver did not verify load-off")
        except Exception as error:  # noqa: BLE001 - map physical stop failure to FAILED
            result = StopResult(StopPhase.FAILED, detail=f"{type(error).__name__}: {error}")
        self.last_stop = result
        event = Event(event_name, device_id, {"phase": result.phase.value, "already_safe": result.already_safe})
        self.pending_events.append(event)
        try:
            self.bus.publish(event)
            self.pending_events.remove(event)
        except Exception as error:  # noqa: BLE001 - persistence failure cannot mask stop result
            # Persistence failure is recorded in memory; caller still receives the stop result.
            self.event_dispatch_errors.append(error)
        return result

    def request_safe_shutdown(self, control: ISafetyControllable, device_id: str) -> StopResult:
        return self._stop(control, device_id, "SafetyShutdown")

    def emergency_stop(self, control: ISafetyControllable, device_id: str) -> StopResult:
        return self._stop(control, device_id, "EmergencyStopTriggered")
