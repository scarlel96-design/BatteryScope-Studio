"""Replay canonical CSV or Parquet records with explicit replay provenance."""

from __future__ import annotations

import csv
import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Iterable

import pyarrow.parquet as pq

from batteryscope.core.models import DeviceCapabilities, DeviceIdentity, MeasurementSample, QualityFlag, SourceKind, SupportStatus
from batteryscope.core.errors import ReplayError
from batteryscope.devices.virtual.devices import Clock, host_clock


class ReplayMode(StrEnum):
    REALTIME = "REALTIME"
    ACCELERATED = "ACCELERATED"
    MAX_SPEED = "MAX_SPEED"
    STEP = "STEP"


class ReplayDevice:
    def __init__(self, path: Path, clock: Clock = host_clock, mode: ReplayMode = ReplayMode.MAX_SPEED,
                 expected_sha256: str | None = None) -> None:
        if path.suffix.lower() not in (".csv", ".parquet"):
            raise ValueError("replay supports CSV or Parquet")
        self.path = path
        self.clock = clock
        self.mode = mode
        self.expected_sha256 = expected_sha256
        if mode != ReplayMode.MAX_SPEED:
            raise NotImplementedError(f"replay mode {mode} is reserved")
        self.connected = False

    @classmethod
    def discover(cls) -> list[DeviceIdentity]:
        return []  # Replay sources are selected explicitly by path.

    def connect(self) -> None:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        if self.expected_sha256 is not None:
            digest = hashlib.sha256()
            with self.path.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    digest.update(block)
            if digest.hexdigest() != self.expected_sha256:
                raise ReplayError("replay source checksum differs from registered raw chunk")
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def get_identity(self) -> DeviceIdentity:
        return DeviceIdentity(device_id="replay:source", display_name=f"Replay: {self.path.name}", kind=SourceKind.REPLAYED,
                              discovery_status=SupportStatus.VERIFIED, telemetry_status=SupportStatus.VERIFIED,
                              control_status=SupportStatus.NOT_IMPLEMENTED, evidence=(str(self.path),))

    def get_capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(features=frozenset({"measurement.voltage", "measurement.current", "measurement.power"}))

    def get_status(self) -> str:
        return "CONNECTED" if self.connected else "DISCONNECTED"

    def self_test(self) -> bool:
        return self.connected

    def provenance(self) -> str:
        return str(self.path)

    def _rows(self) -> Iterable[dict]:
        if self.path.suffix.lower() == ".parquet":
            yield from pq.read_table(self.path).to_pylist()
        else:
            with self.path.open(newline="", encoding="utf-8") as handle:
                yield from csv.DictReader(handle)

    def samples(self, count: int) -> Iterable[MeasurementSample]:
        if not self.connected:
            raise RuntimeError("replay device disconnected")
        for index, row in enumerate(self._rows()):
            if index >= count:
                break
            stamp_ns, stamp_utc = self.clock()
            extras = json.loads(row.get("extras_json") or "{}")
            extras["replay_source"] = str(self.path)
            extras["original_timestamp_utc"] = str(row.get("timestamp_utc", ""))
            extras["original_timestamp_monotonic_ns"] = row.get("timestamp_monotonic_ns")
            extras["original_sequence"] = int(row["sequence"])
            extras["original_source_device_id"] = str(row.get("source_device_id", ""))
            extras["replay_ingest_timestamp_monotonic_ns"] = stamp_ns
            extras["replay_ingest_timestamp_utc"] = stamp_utc.isoformat()
            extras["replay_sequence"] = index + 1
            extras["replay_mode"] = self.mode.value
            yield MeasurementSample(
                timestamp_monotonic_ns=stamp_ns, timestamp_utc=stamp_utc,
                sequence=index + 1, source_device_id="replay:source", source_kind=SourceKind.REPLAYED,
                voltage_v=float(row["voltage_v"]), current_a=float(row["current_a"]),
                power_w=float(row["power_w"]),
                device_temperature_c=float(row["device_temperature_c"]) if row.get("device_temperature_c") else None,
                accumulated_ah=float(row["accumulated_ah"]) if row.get("accumulated_ah") else None,
                accumulated_wh=float(row["accumulated_wh"]) if row.get("accumulated_wh") else None,
                quality_flags=frozenset({QualityFlag.VALID, QualityFlag.REPLAYED}), extras=extras,
            )
