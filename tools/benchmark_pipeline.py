"""Optional performance baseline; deliberately separate from pytest gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from batteryscope.app.service import run_virtual_demo
from batteryscope.core.config import AppConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-device", type=int, default=10000)
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime/benchmarks"))
    args = parser.parse_args()
    if args.samples_per_device < 1:
        parser.error("samples-per-device must be positive")
    result = run_virtual_demo(AppConfig(runtime_dir=args.runtime_dir), sample_count=args.samples_per_device)
    summary = {key: result[key] for key in (
        "session_id", "rows", "raw_chunks", "queue_max_depth", "ingestion_samples_per_second",
        "duckdb_query_ms", "chunk_write_bytes_per_second", "status", "emergency_stop_phase")}
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
