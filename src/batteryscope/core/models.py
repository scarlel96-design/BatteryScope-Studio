"""Canonical contracts shared by drivers, acquisition, and storage."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    OBSERVED = "OBSERVED"
    USER_SUPPLIED = "USER_SUPPLIED"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"
    SIMULATED = "SIMULATED"
    TEST_FIXTURE = "TEST_FIXTURE"


class LimitSourceKind(StrEnum):
    PHYSICAL_DOCUMENT = "PHYSICAL_DOCUMENT"
    PHYSICAL_OBSERVATION = "PHYSICAL_OBSERVATION"
    USER_INPUT = "USER_INPUT"
    TEST_FIXTURE = "TEST_FIXTURE"
    UNKNOWN = "UNKNOWN"


class SupportStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class SourceKind(StrEnum):
    REAL = "REAL"
    SIMULATED = "SIMULATED"
    REPLAYED = "REPLAYED"


class QualityFlag(StrEnum):
    VALID = "VALID"
    DATA_GAP = "DATA_GAP"
    DEVICE_RECONNECT = "DEVICE_RECONNECT"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    SENSOR_WARNING = "SENSOR_WARNING"
    SIMULATED = "SIMULATED"
    REPLAYED = "REPLAYED"
    DROPPED_SAMPLE = "DROPPED_SAMPLE"
    BACKPRESSURE_OVERFLOW = "BACKPRESSURE_OVERFLOW"


class VerifiedValue(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: float | None = None
    unit: str
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    source: str | None = None
    source_kind: LimitSourceKind = LimitSourceKind.UNKNOWN
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def consistent(self) -> "VerifiedValue":
        if self.verification_status == VerificationStatus.UNKNOWN and self.value is not None:
            raise ValueError("UNKNOWN value must be absent")
        if self.verification_status != VerificationStatus.UNKNOWN and self.value is None:
            raise ValueError("known status requires a value")
        if self.value is not None and (self.value <= 0 or not isfinite(self.value)):
            raise ValueError("limit must be positive")
        if self.verification_status == VerificationStatus.VERIFIED and not self.source:
            raise ValueError("VERIFIED requires source")
        if self.verification_status == VerificationStatus.VERIFIED and self.source_kind not in (
            LimitSourceKind.PHYSICAL_DOCUMENT, LimitSourceKind.PHYSICAL_OBSERVATION
        ):
            raise ValueError("VERIFIED physical limit requires physical provenance")
        if self.verification_status in (VerificationStatus.SIMULATED, VerificationStatus.TEST_FIXTURE) and self.source_kind != LimitSourceKind.TEST_FIXTURE:
            raise ValueError("simulated limit requires test fixture provenance")
        return self


class DeviceCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)
    features: frozenset[str] = frozenset()
    max_voltage: VerifiedValue = Field(default_factory=lambda: VerifiedValue(unit="V"))
    max_current: VerifiedValue = Field(default_factory=lambda: VerifiedValue(unit="A"))
    max_power: VerifiedValue = Field(default_factory=lambda: VerifiedValue(unit="W"))
    sample_rate_hz: VerifiedValue = Field(default_factory=lambda: VerifiedValue(unit="Hz"))

    def supports(self, feature: str) -> bool:
        return feature in self.features


class DeviceIdentity(BaseModel):
    device_id: str
    display_name: str
    kind: SourceKind
    discovery_status: SupportStatus
    telemetry_status: SupportStatus
    control_status: SupportStatus
    evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def namespace_matches_kind(self) -> "DeviceIdentity":
        prefix = {SourceKind.REAL: "physical:", SourceKind.SIMULATED: "virtual:", SourceKind.REPLAYED: "replay:"}[self.kind]
        if not self.device_id.startswith(prefix):
            raise ValueError(f"device_id must start with {prefix}")
        return self


class MeasurementSample(BaseModel):
    """Host receipt time is authoritative; device time belongs in extras."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    timestamp_monotonic_ns: int = Field(ge=0)
    timestamp_utc: datetime
    sequence: int = Field(ge=0)
    source_device_id: str = Field(min_length=1)
    source_kind: SourceKind
    voltage_v: float = Field(ge=0, allow_inf_nan=False)
    current_a: float = Field(ge=0, allow_inf_nan=False)
    power_w: float = Field(ge=0, allow_inf_nan=False)
    device_temperature_c: float | None = Field(default=None, allow_inf_nan=False)
    accumulated_ah: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    accumulated_wh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    quality_flags: frozenset[QualityFlag] = frozenset({QualityFlag.VALID})
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp_utc")
    @classmethod
    def utc_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTC timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def provenance(self) -> "MeasurementSample":
        prefix = {SourceKind.REAL: "physical:", SourceKind.SIMULATED: "virtual:", SourceKind.REPLAYED: "replay:"}[self.source_kind]
        if not self.source_device_id.startswith(prefix):
            raise ValueError(f"source_device_id must start with {prefix}")
        required = {
            SourceKind.SIMULATED: QualityFlag.SIMULATED,
            SourceKind.REPLAYED: QualityFlag.REPLAYED,
        }.get(self.source_kind)
        if required and required not in self.quality_flags:
            raise ValueError("source kind requires corresponding quality flag")
        if not self.quality_flags:
            raise ValueError("quality flags required")
        return self


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    name: str
    vendor: str
    version: str
    supported_devices: tuple[str, ...]
    capabilities: tuple[str, ...]
    minimum_app_version: str
