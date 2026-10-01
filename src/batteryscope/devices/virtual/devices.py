"""Clearly simulated meters and load for development and replay tests."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from time import monotonic_ns
from typing import Callable, Iterable

from batteryscope.core.models import (
    DeviceCapabilities, DeviceIdentity, MeasurementSample, QualityFlag,
    SourceKind, SupportStatus, VerifiedValue, VerificationStatus, LimitSourceKind,
)
from batteryscope.safety.stop import StopPhase, StopResult
from batteryscope.devices.virtual.battery import VirtualBattery
from batteryscope.devices.virtual.scenarios import SCENARIOS


Clock = Callable[[], tuple[int, datetime]]


def host_clock() -> tuple[int, datetime]:
    return monotonic_ns(), datetime.now(timezone.utc)


def simulated_limit(value: float, unit: str) -> VerifiedValue:
    return VerifiedValue(value=value, unit=unit, verification_status=VerificationStatus.SIMULATED,
                         source_kind=LimitSourceKind.TEST_FIXTURE, source="virtual fixture")


class LoadState(StrEnum):
    IDLE = "IDLE"
    CC = "CC"
    CP = "CP"
    LOAD_OFF = "LOAD_OFF"
    SAFE = "SAFE"


class VirtualC2:
    simulator_version = "0.1.0"

    def __init__(self, scenario: str = "normal", clock: Clock = host_clock, seed: int = 0) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        self.scenario = scenario
        self.seed = seed
        self.clock = clock
        self.connected = False
        self.sequence = 0

    @classmethod
    def discover(cls) -> list[DeviceIdentity]:
        return [cls().get_identity()]

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def get_identity(self) -> DeviceIdentity:
        return DeviceIdentity(device_id="virtual:c2", display_name="Virtual C2", kind=SourceKind.SIMULATED,
                              discovery_status=SupportStatus.VERIFIED, telemetry_status=SupportStatus.VERIFIED,
                              control_status=SupportStatus.NOT_IMPLEMENTED, evidence=("simulation",))

    def get_capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(features=frozenset({"measurement.voltage", "measurement.current", "measurement.power"}),
                                  sample_rate_hz=simulated_limit(50, "Hz"))

    def get_status(self) -> str:
        return "CONNECTED" if self.connected else "DISCONNECTED"

    def self_test(self) -> bool:
        return self.connected

    def samples(self, count: int) -> Iterable[MeasurementSample]:
        if not self.connected:
            raise RuntimeError("virtual C2 disconnected")
        for _ in range(count):
            self.sequence += 1
            effect = SCENARIOS[self.scenario](self.sequence)
            if effect.disconnect:
                self.disconnect()
                raise ConnectionError("simulated C2 disconnect")
            if effect.data_gap:
                self.sequence += 1
            voltage_v = 20.0 * effect.voltage_multiplier
            current_a = 2.0
            stamp_ns, stamp_utc = self.clock()
            flags = {QualityFlag.SIMULATED, QualityFlag.VALID}
            if effect.data_gap:
                flags.add(QualityFlag.DATA_GAP)
            if effect.sensor_warning:
                flags.add(QualityFlag.SENSOR_WARNING)
            extras = {"pd_renegotiation": effect.pd_renegotiation, "pdo": "mock-20v"}
            yield MeasurementSample(timestamp_monotonic_ns=stamp_ns, timestamp_utc=stamp_utc,
                                    sequence=self.sequence, source_device_id="virtual:c2", source_kind=SourceKind.SIMULATED,
                                    voltage_v=voltage_v, current_a=current_a, power_w=voltage_v * current_a,
                                    quality_flags=frozenset(flags), extras=extras)


class VirtualEBD:
    simulator_version = "0.1.0"

    def __init__(self, battery: VirtualBattery | None = None, scenario: str = "normal", clock: Clock = host_clock,
                 interval_s: float = 0.02, seed: int = 0) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        self.battery = battery or VirtualBattery()
        self.scenario = scenario
        self.seed = seed
        self.clock = clock
        self.interval_s = interval_s
        self.connected = False
        self.state = LoadState.IDLE
        self.setpoint_a = 0.0
        self.setpoint_w = 0.0
        self.load_enabled = False
        self.sequence = 0
        self.accumulated_ah = 0.0
        self.accumulated_wh = 0.0
        self.last_stop = StopResult(StopPhase.VERIFIED_OFF, already_safe=True)
        self.stop_history: list[StopPhase] = []

    @classmethod
    def discover(cls) -> list[DeviceIdentity]:
        return [cls().get_identity()]

    def connect(self) -> None:
        self.connected = True
        self.state = LoadState.IDLE
        self.load_enabled = False

    def disconnect(self) -> None:
        self.connected = False
        self.emergency_stop()

    def get_identity(self) -> DeviceIdentity:
        return DeviceIdentity(device_id="virtual:ebd", display_name="Virtual EBD", kind=SourceKind.SIMULATED,
                              discovery_status=SupportStatus.VERIFIED, telemetry_status=SupportStatus.VERIFIED,
                              control_status=SupportStatus.VERIFIED, evidence=("simulation",))

    def get_capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(features=frozenset({"measurement.voltage", "measurement.current", "measurement.power",
                                                    "load.constant_current", "load.constant_power", "emergency_stop"}),
                                  max_voltage=simulated_limit(30, "V"), max_current=simulated_limit(10, "A"),
                                  max_power=simulated_limit(200, "W"), sample_rate_hz=simulated_limit(50, "Hz"))

    def get_status(self) -> str:
        return self.state.value if self.connected else "DISCONNECTED"

    def self_test(self) -> bool:
        return self.connected and self.state in (LoadState.IDLE, LoadState.LOAD_OFF, LoadState.SAFE)

    def set_constant_current(self, current_a: float) -> None:
        if current_a < 0 or not self.connected:
            raise ValueError("invalid current or disconnected")
        self.setpoint_a = current_a
        self.load_enabled = False
        self.state = LoadState.CC

    def set_constant_power(self, power_w: float) -> None:
        if power_w < 0 or not self.connected:
            raise ValueError("invalid power or disconnected")
        self.setpoint_w = power_w
        self.load_enabled = False
        self.state = LoadState.CP

    def load_on(self) -> None:
        if not self.connected or self.state not in (LoadState.CC, LoadState.CP):
            raise RuntimeError("load mode not configured")
        self.load_enabled = True

    def load_off(self) -> None:
        self.load_enabled = False
        self.setpoint_a = 0.0
        self.setpoint_w = 0.0
        self.state = LoadState.LOAD_OFF

    def emergency_stop(self) -> StopResult:
        already_safe = self.state in (LoadState.SAFE, LoadState.LOAD_OFF, LoadState.IDLE)
        self.last_stop = StopResult(StopPhase.REQUESTED, already_safe)
        self.stop_history.append(StopPhase.REQUESTED)
        self.load_off()
        self.last_stop = StopResult(StopPhase.ACKNOWLEDGED, already_safe)
        self.stop_history.append(StopPhase.ACKNOWLEDGED)
        self.state = LoadState.SAFE
        self.last_stop = StopResult(StopPhase.VERIFIED_OFF, already_safe)
        self.stop_history.append(StopPhase.VERIFIED_OFF)
        return self.last_stop

    def samples(self, count: int) -> Iterable[MeasurementSample]:
        if not self.connected:
            raise RuntimeError("virtual EBD disconnected")
        for _ in range(count):
            self.sequence += 1
            effect = SCENARIOS[self.scenario](self.sequence)
            if effect.disconnect:
                self.disconnect()
                raise ConnectionError("simulated EBD disconnect")
            if effect.data_gap:
                self.sequence += 1
            if effect.load_failure or effect.cutoff:
                self.emergency_stop()
            current_a = self.setpoint_a if self.load_enabled and self.state == LoadState.CC else (
                self.setpoint_w / self.battery.nominal_voltage_v if self.load_enabled and self.state == LoadState.CP else 0.0)
            voltage_v, current_a = self.battery.draw(current_a, self.interval_s)
            voltage_v *= effect.voltage_multiplier
            power_w = voltage_v * current_a
            self.accumulated_ah += current_a * self.interval_s / 3600
            self.accumulated_wh += power_w * self.interval_s / 3600
            stamp_ns, stamp_utc = self.clock()
            flags = {QualityFlag.VALID, QualityFlag.SIMULATED}
            if effect.data_gap:
                flags.add(QualityFlag.DATA_GAP)
            if effect.sensor_warning:
                flags.add(QualityFlag.SENSOR_WARNING)
            yield MeasurementSample(timestamp_monotonic_ns=stamp_ns, timestamp_utc=stamp_utc,
                                    sequence=self.sequence, source_device_id="virtual:ebd", source_kind=SourceKind.SIMULATED,
                                    voltage_v=voltage_v, current_a=current_a, power_w=power_w,
                                    accumulated_ah=self.accumulated_ah, accumulated_wh=self.accumulated_wh,
                                    quality_flags=frozenset(flags), extras={"load_state": self.state.value})
