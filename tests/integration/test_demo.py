import json
import sqlite3

import duckdb
import pyarrow.parquet as pq

from batteryscope.app.service import run_virtual_demo
from batteryscope.core.config import AppConfig, Environment


def test_full_virtual_path(tmp_path) -> None:
    result = run_virtual_demo(AppConfig(environment=Environment.TEST, runtime_dir=tmp_path,
                                        chunk_max_rows=4), sample_count=6)
    assert result["status"] == "ABORTED"
    assert result["rows"] == 12
    assert result["load_state"] == "SAFE"
    session = tmp_path / "sessions" / result["session_id"]
    files = list((session / "raw").glob("*.parquet"))
    assert len(files) >= 2
    assert all(pq.read_metadata(file).row_group(0).column(0).compression == "ZSTD" for file in files)
    assert {row[0] for row in duckdb.connect().execute(
        "SELECT DISTINCT source_kind FROM read_parquet(?)", [str(session / "raw" / "*.parquet")]
    ).fetchall()} == {"SIMULATED"}
    with sqlite3.connect(tmp_path / "metadata.sqlite3") as db:
        assert db.execute("SELECT status FROM sessions").fetchone()[0] == "ABORTED"
        assert db.execute("SELECT count(*) FROM raw_chunks").fetchone()[0] == len(files)
        assert db.execute("SELECT count(*) FROM events WHERE name='EmergencyStopTriggered'").fetchone()[0] == 1
    events = (session / "events" / "events.jsonl").read_text(encoding="utf-8")
    assert "EmergencyStopTriggered" in events
    assert json.loads((session / "manifest.json").read_text())["status"] == "ABORTED"
    assert result["emergency_stop_phase"] == "VERIFIED_OFF"
