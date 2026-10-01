from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from batteryscope.core.events import EventBus
from batteryscope.core.models import (
    DeviceCapabilities, MeasurementSample, QualityFlag, SourceKind,
    VerificationStatus, VerifiedValue,
)
from batteryscope.devices.virtual.devices import LoadState, VirtualEBD
from batteryscope.safety.engine import LoadRequest, SafetyDenied, SafetyEngine


def test_capability_and_verified_value() -> None:
    caps = DeviceCapabilities(features=frozenset({"load.constant_current"}))
    assert caps.supports("load.constant_current")
    assert not caps.supports("load.constant_power")
    with pytest.raises(ValidationError):
        VerifiedValue(value=30, unit="V", verification_status=VerificationStatus.UNKNOWN)


def test_unknown_physical_limit_denies_load() -> None:
    engine = SafetyEngine(EventBus())
    caps = DeviceCapabilities(features=frozenset({"load.constant_current"}))
    with pytest.raises(SafetyDenied, match="not VERIFIED"):
        engine.validate_requested_load(LoadRequest(mode="CC", current_a=1, voltage_v=5), caps, SourceKind.REAL)


def test_emergency_stop_turns_virtual_load_off_and_safe() -> None:
    ebd = VirtualEBD()
    ebd.connect()
    ebd.set_constant_current(2)
    ebd.load_on()
    assert ebd.state == LoadState.CC
    engine = SafetyEngine(EventBus())
    engine.emergency_stop(ebd, "virtual-ebd")
    assert ebd.state == LoadState.SAFE
    assert ebd.setpoint_a == 0
    assert next(iter(ebd.samples(1))).current_a == 0
    engine.emergency_stop(ebd, "virtual-ebd")
    assert ebd.state == LoadState.SAFE


def test_sample_rejects_nonfinite_and_missing_provenance() -> None:
    common = dict(timestamp_monotonic_ns=1, timestamp_utc=datetime.now(timezone.utc),
                  sequence=1, source_device_id="virtual:test", source_kind=SourceKind.SIMULATED,
                  voltage_v=5, current_a=1, power_w=5)
    with pytest.raises(ValidationError):
        MeasurementSample(**common, quality_flags={QualityFlag.VALID})
    with pytest.raises(ValidationError):
        MeasurementSample(**{**common, "voltage_v": float("nan")},
                          quality_flags={QualityFlag.SIMULATED})
    with pytest.raises(ValidationError):
        MeasurementSample(**{**common, "current_a": -1}, quality_flags={QualityFlag.SIMULATED})
