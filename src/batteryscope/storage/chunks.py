"""Arrow schema and atomic Parquet/ZSTD chunk persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from batteryscope.core.models import MeasurementSample
from batteryscope.storage.session import SessionStore


SAMPLE_SCHEMA = pa.schema([
    ("timestamp_monotonic_ns", pa.int64()),
    ("timestamp_utc", pa.timestamp("us", tz="UTC")),
    ("sequence", pa.int64()),
    ("source_device_id", pa.string()),
    ("source_kind", pa.string()),
    ("voltage_v", pa.float64()),
    ("current_a", pa.float64()),
    ("power_w", pa.float64()),
    ("device_temperature_c", pa.float64()),
    ("accumulated_ah", pa.float64()),
    ("accumulated_wh", pa.float64()),
    ("quality_flags", pa.list_(pa.string())),
    ("extras_json", pa.string()),
])


def sample_record(sample: MeasurementSample) -> dict:
    return {
        "timestamp_monotonic_ns": sample.timestamp_monotonic_ns,
        "timestamp_utc": sample.timestamp_utc,
        "sequence": sample.sequence,
        "source_device_id": sample.source_device_id,
        "source_kind": sample.source_kind.value,
        "voltage_v": sample.voltage_v,
        "current_a": sample.current_a,
        "power_w": sample.power_w,
        "device_temperature_c": sample.device_temperature_c,
        "accumulated_ah": sample.accumulated_ah,
        "accumulated_wh": sample.accumulated_wh,
        "quality_flags": sorted(flag.value for flag in sample.quality_flags),
        "extras_json": json.dumps(sample.extras, sort_keys=True, allow_nan=False),
    }


class ChunkWriter:
    def __init__(self, store: SessionStore, session_id: str, session_path: Path) -> None:
        self.store = store
        self.session_id = session_id
        self.session_path = session_path
        self.indices: dict[str, int] = {}

    def write(self, device_id: str, samples: list[MeasurementSample]) -> Path:
        if not samples:
            raise ValueError("empty chunk")
        if any(sample.source_device_id != device_id for sample in samples):
            raise ValueError("mixed device chunk")
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", device_id)
        if device_id not in self.indices:
            existing = sorted((self.session_path / "raw").glob(f"{safe_id}_*.parquet"))
            self.indices[device_id] = max((int(p.stem.rsplit("_", 1)[-1]) for p in existing), default=0)
        index = self.indices[device_id] + 1
        relative = Path("raw") / f"{safe_id}_{index:06d}.parquet"
        final_path = self.session_path / relative
        temp_path = final_path.with_suffix(".parquet.tmp")
        if final_path.exists():
            raise FileExistsError(final_path)
        table = pa.Table.from_pylist([sample_record(sample) for sample in samples], schema=SAMPLE_SCHEMA)
        pq.write_table(table, temp_path, compression="zstd")
        # pyarrow has closed its handle before Windows finalization begins.
        with temp_path.open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
            digest = hashlib.sha256()
            file_size = 0
            while block := handle.read(1024 * 1024):
                digest.update(block)
                file_size += len(block)
        sha256 = digest.hexdigest()
        os.replace(temp_path, final_path)
        self.store.add_chunk(self.session_id, device_id, relative.as_posix(), len(samples), sha256,
                             min(s.timestamp_monotonic_ns for s in samples),
                             max(s.timestamp_monotonic_ns for s in samples), file_size,
                             samples[0].sequence, samples[-1].sequence)
        self.indices[device_id] = index
        return final_path
