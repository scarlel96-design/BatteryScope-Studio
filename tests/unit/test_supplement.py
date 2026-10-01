import pytest
from pydantic import ValidationError

from batteryscope.core.errors import StorageError
from batteryscope.app.stop_channel import EmergencyStopChannel
from batteryscope.core.events import EventBus
from batteryscope.core.models import DeviceCapabilities, LimitSourceKind, SourceKind, VerificationStatus, VerifiedValue
from batteryscope.devices.base.contracts import NotVerifiedProtocolError
from batteryscope.devices.c2.driver import C2ProDriver
from batteryscope.devices.ebd.driver import EBDA20HDriver
from batteryscope.devices.virtual.devices import VirtualEBD
from batteryscope.plugins.registry import PluginRegistry
from batteryscope.core.models import PluginManifest
from batteryscope.safety.engine import LoadRequest, SafetyDenied, SafetyEngine
from batteryscope.safety.stop import StopPhase


def test_simulated_limit_never_authorizes_physical_automatic_load() -> None:
    fixture = VerifiedValue(value=500, unit="W", source="fixture", source_kind=LimitSourceKind.TEST_FIXTURE,
                            verification_status=VerificationStatus.SIMULATED)
    caps = DeviceCapabilities(features=frozenset({"load.constant_power"}), max_power=fixture)
    with pytest.raises(SafetyDenied):
        SafetyEngine(EventBus()).validate_requested_load(
            LoadRequest(mode="CP", power_w=1), caps, SourceKind.REAL)
    with pytest.raises(ValidationError):
        VerifiedValue(value=500, unit="W", source="fixture", source_kind=LimitSourceKind.TEST_FIXTURE,
                      verification_status=VerificationStatus.VERIFIED)


def test_unknown_cp_limit_denies_even_one_watt() -> None:
    caps = DeviceCapabilities(features=frozenset({"load.constant_power"}))
    with pytest.raises(SafetyDenied, match="not VERIFIED"):
        SafetyEngine(EventBus()).validate_requested_load(
            LoadRequest(mode="CP", power_w=1), caps, SourceKind.REAL)


def test_physical_write_paths_fail_closed() -> None:
    c2 = C2ProDriver()
    ebd = EBDA20HDriver()
    for action in (lambda: c2.request_pdo(1), lambda: c2.request_pps(5, 1),
                   lambda: c2.firmware_command(b"x"), lambda: ebd.set_current(1),
                   lambda: ebd.set_power(1), ebd.load_on, ebd.load_off, ebd.emergency_stop):
        with pytest.raises(NotVerifiedProtocolError):
            action()


def test_emergency_stop_survives_event_storage_failure() -> None:
    ebd = VirtualEBD()
    ebd.connect()
    ebd.set_constant_current(2)
    ebd.load_on()
    bus = EventBus()
    bus.subscribe("*", lambda _: (_ for _ in ()).throw(StorageError("disk full")))
    safety = SafetyEngine(bus)
    result = safety.emergency_stop(ebd, "virtual:ebd")
    assert result.phase == StopPhase.VERIFIED_OFF
    assert ebd.state.value == "SAFE"
    assert len(safety.pending_events) == 1
    assert isinstance(safety.event_dispatch_errors[0], StorageError)
    assert safety.emergency_stop(ebd, "virtual:ebd").already_safe


def test_registry_rejects_false_emergency_stop_claim() -> None:
    class BadDevice:
        def get_capabilities(self):
            return DeviceCapabilities(features=frozenset({"emergency_stop"}))

    manifest = PluginManifest(plugin_id="bad.device", name="Bad", vendor="Fixture", version="1",
                              supported_devices=("virtual:bad",), capabilities=("emergency_stop",),
                              minimum_app_version="0.1")
    with pytest.raises(ValueError, match="requires"):
        PluginRegistry().register(manifest, BadDevice)


def test_virtual_mode_selection_does_not_energize_load() -> None:
    ebd = VirtualEBD()
    ebd.connect()
    ebd.set_constant_current(2)
    assert next(iter(ebd.samples(1))).current_a == 0
    ebd.load_on()
    assert next(iter(ebd.samples(1))).current_a > 0
    ebd.load_off()
    assert next(iter(ebd.samples(1))).current_a == 0


def test_priority_stop_channel_requests_safe_state() -> None:
    ebd = VirtualEBD()
    ebd.connect()
    ebd.set_constant_current(2)
    ebd.load_on()
    channel = EmergencyStopChannel()
    channel.arm(ebd, SafetyEngine(EventBus()), "virtual:ebd")
    channel.request()
    channel.request()
    assert channel.finish().phase == StopPhase.VERIFIED_OFF
    assert ebd.state.value == "SAFE"
