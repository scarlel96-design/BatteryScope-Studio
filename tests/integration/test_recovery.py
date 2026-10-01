import hashlib
import sqlite3

from batteryscope.core.config import AppConfig
from batteryscope.devices.virtual.devices import VirtualC2
from batteryscope.storage.chunks import ChunkWriter
from batteryscope.storage.session import SessionState, SessionStore


def test_interrupted_session_and_orphan_recovery(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session_id, path = store.create_session()
    store.transition(session_id, path, SessionState.RUNNING)
    (path / "raw" / "interrupted.parquet.tmp").write_bytes(b"partial")
    (path / "raw" / "orphan.parquet").write_bytes(b"complete but unregistered")
    store.close()
    reopened = SessionStore(tmp_path)
    issues = reopened.recover_incomplete()
    assert reopened.state(session_id) == SessionState.INCOMPLETE
    assert {issue["kind"] for issue in issues} == {"INTERRUPTED", "RECOVERABLE", "ORPHAN"}
    assert (path / "raw" / "interrupted.parquet.tmp").exists()
    assert (path / "raw" / "orphan.parquet").exists()
    reopened.close()


def test_chunk_windows_finalize_and_integrity(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session_id, path = store.create_session()
    c2 = VirtualC2()
    c2.connect()
    target = ChunkWriter(store, session_id, path).write("virtual:c2", list(c2.samples(3)))
    assert target.exists() and not target.with_suffix(".parquet.tmp").exists()
    assert store.verify_chunks(session_id) == []
    with sqlite3.connect(store.db_path) as db:
        size, rows, first, last, digest = db.execute(
            "SELECT file_size,row_count,first_sequence,last_sequence,sha256 FROM raw_chunks"
        ).fetchone()
    assert (size, rows, first, last, digest) == (target.stat().st_size, 3, 1, 3,
                                               hashlib.sha256(target.read_bytes()).hexdigest())
    store.close()


def test_two_sessions_can_register_same_relative_chunk_name(tmp_path) -> None:
    store = SessionStore(tmp_path)
    for _ in range(2):
        session_id, path = store.create_session()
        c2 = VirtualC2()
        c2.connect()
        store.add_device(session_id, "virtual:c2", "Virtual C2", "SIMULATED")
        ChunkWriter(store, session_id, path).write("virtual:c2", list(c2.samples(1)))
    with sqlite3.connect(store.db_path) as db:
        assert db.execute("SELECT count(*) FROM session_devices").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM raw_chunks").fetchone()[0] == 2
        assert db.execute("SELECT count(DISTINCT relative_path) FROM raw_chunks").fetchone()[0] == 1
    store.close()


def test_schema_v2_migrates_chunk_uniqueness_to_session_scope(tmp_path) -> None:
    old = SessionStore(tmp_path)
    old.connection.execute("DROP TABLE raw_chunks")
    old.connection.execute("""CREATE TABLE raw_chunks (
        chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        device_id TEXT NOT NULL, relative_path TEXT NOT NULL UNIQUE,
        row_count INTEGER NOT NULL, sha256 TEXT NOT NULL,
        min_monotonic_ns INTEGER NOT NULL, max_monotonic_ns INTEGER NOT NULL,
        file_size INTEGER NOT NULL DEFAULT 0, first_sequence INTEGER NOT NULL DEFAULT 0,
        last_sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id))""")
    old.connection.execute("UPDATE schema_info SET version=2")
    old.connection.commit()
    old.close()
    migrated = SessionStore(tmp_path)
    assert migrated.connection.execute("SELECT version FROM schema_info").fetchone()[0] == 3
    for _ in range(2):
        sid, _ = migrated.create_session()
        migrated.add_chunk(sid, "virtual:c2", "raw/same.parquet", 1, "0" * 64, 1, 1, 1, 1, 1)
    assert migrated.connection.execute("SELECT count(*) FROM raw_chunks").fetchone()[0] == 2
    migrated.close()
