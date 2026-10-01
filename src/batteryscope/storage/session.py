"""Transactional SQLite metadata, explicit lifecycle, and non-destructive recovery."""

from __future__ import annotations

import json
import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Callable
from uuid import uuid4

from batteryscope.core.errors import StorageError
from batteryscope.core.events import Event
from batteryscope import __version__


SCHEMA_VERSION = 3
Migration = Callable[[sqlite3.Connection], None]


class SessionState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    ABORTED = "ABORTED"
    FAILED = "FAILED"


TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.CREATED: frozenset({SessionState.RUNNING, SessionState.INCOMPLETE, SessionState.FAILED}),
    SessionState.RUNNING: frozenset({SessionState.STOPPING, SessionState.INCOMPLETE, SessionState.FAILED}),
    SessionState.STOPPING: frozenset({SessionState.COMPLETE, SessionState.ABORTED, SessionState.INCOMPLETE, SessionState.FAILED}),
}


def _migrate_1_to_2(connection: sqlite3.Connection) -> None:
    for statement in (
        "ALTER TABLE sessions ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE raw_chunks ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE raw_chunks ADD COLUMN first_sequence INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE raw_chunks ADD COLUMN last_sequence INTEGER NOT NULL DEFAULT 0",
    ):
        connection.execute(statement)


def _migrate_2_to_3(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE raw_chunks_new (
          chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
          device_id TEXT NOT NULL, relative_path TEXT NOT NULL,
          row_count INTEGER NOT NULL, sha256 TEXT NOT NULL,
          min_monotonic_ns INTEGER NOT NULL, max_monotonic_ns INTEGER NOT NULL,
          file_size INTEGER NOT NULL DEFAULT 0,
          first_sequence INTEGER NOT NULL DEFAULT 0,
          last_sequence INTEGER NOT NULL DEFAULT 0,
          UNIQUE(session_id, relative_path),
          FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )""")
    connection.execute("INSERT INTO raw_chunks_new SELECT * FROM raw_chunks")
    connection.execute("DROP TABLE raw_chunks")
    connection.execute("ALTER TABLE raw_chunks_new RENAME TO raw_chunks")


MIGRATIONS: dict[int, Migration] = {1: _migrate_1_to_2, 2: _migrate_2_to_3}


class SessionStore:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = runtime_dir / "metadata.sqlite3"
        self._lock = RLock()
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._create_schema()
        with self._lock, self.connection:
            self.connection.execute("INSERT OR IGNORE INTO app_versions VALUES (?,?)",
                                    (__version__, datetime.now(timezone.utc).isoformat()))

    def _create_schema(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY, path TEXT NOT NULL, status TEXT NOT NULL,
              started_at TEXT NOT NULL, ended_at TEXT, provenance_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS devices (
              device_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, kind TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_devices (
              session_id TEXT NOT NULL, device_id TEXT NOT NULL,
              PRIMARY KEY(session_id, device_id),
              FOREIGN KEY(session_id) REFERENCES sessions(session_id),
              FOREIGN KEY(device_id) REFERENCES devices(device_id)
            );
            CREATE TABLE IF NOT EXISTS events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
              timestamp_utc TEXT NOT NULL, name TEXT NOT NULL, device_id TEXT,
              details_json TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE TABLE IF NOT EXISTS raw_chunks (
              chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
              device_id TEXT NOT NULL, relative_path TEXT NOT NULL,
              row_count INTEGER NOT NULL, sha256 TEXT NOT NULL,
              min_monotonic_ns INTEGER NOT NULL, max_monotonic_ns INTEGER NOT NULL,
              file_size INTEGER NOT NULL DEFAULT 0,
              first_sequence INTEGER NOT NULL DEFAULT 0,
              last_sequence INTEGER NOT NULL DEFAULT 0,
              UNIQUE(session_id, relative_path),
              FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE TABLE IF NOT EXISTS app_versions (
              version TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL
            );
        """)
        with self.connection:
            row = self.connection.execute("SELECT version FROM schema_info").fetchone()
            if row is None:
                self.connection.execute("INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                self.connection.execute("BEGIN IMMEDIATE")
                version = row[0]
                while version < SCHEMA_VERSION:
                    migration = MIGRATIONS.get(version)
                    if migration is None:
                        raise StorageError(f"missing database migration {version}")
                    migration(self.connection)
                    version += 1
                    self.connection.execute("UPDATE schema_info SET version=?", (version,))
                if version != SCHEMA_VERSION:
                    raise StorageError(f"unsupported database schema version: {version}")

    def recover_incomplete(self) -> list[dict[str, str]]:
        """Mark interrupted sessions and report temp/orphan chunks; preserve all files."""
        issues: list[dict[str, str]] = []
        with self._lock, self.connection:
            rows = self.connection.execute(
                "SELECT session_id,path,status FROM sessions WHERE status IN ('RUNNING','STOPPING')"
            ).fetchall()
            for session_id, path_string, old_status in rows:
                self.connection.execute("UPDATE sessions SET status='INCOMPLETE',ended_at=? WHERE session_id=?",
                                        (datetime.now(timezone.utc).isoformat(), session_id))
                issues.append({"session_id": session_id, "path": path_string, "kind": "INTERRUPTED", "previous": old_status})
            sessions = self.connection.execute("SELECT session_id,path FROM sessions").fetchall()
            for session_id, path_string in sessions:
                raw = Path(path_string) / "raw"
                if not raw.exists():
                    continue
                registered = {row[0] for row in self.connection.execute(
                    "SELECT relative_path FROM raw_chunks WHERE session_id=?", (session_id,)
                )}
                for file in raw.glob("*.tmp"):
                    issues.append({"session_id": session_id, "path": str(file), "kind": "RECOVERABLE"})
                for file in raw.glob("*.parquet"):
                    if file.relative_to(Path(path_string)).as_posix() not in registered:
                        issues.append({"session_id": session_id, "path": str(file), "kind": "ORPHAN"})
        with self._lock:
            current_sessions = self.connection.execute("SELECT session_id,path,status FROM sessions").fetchall()
        for session_id, path_string, db_status in current_sessions:
            manifest_path = Path(path_string) / "manifest.json"
            if not manifest_path.is_file():
                issues.append({"session_id": session_id, "path": str(manifest_path), "kind": "MISSING_MANIFEST"})
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                issues.append({"session_id": session_id, "path": str(manifest_path), "kind": "CORRUPT_MANIFEST"})
                continue
            if manifest.get("status") != db_status:
                if not any(issue["session_id"] == session_id and issue["kind"] == "INTERRUPTED" for issue in issues):
                    issues.append({"session_id": session_id, "path": str(manifest_path), "kind": "MANIFEST_MISMATCH"})
                manifest["status"] = db_status
                temp = manifest_path.with_suffix(".json.tmp")
                temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                os.replace(temp, manifest_path)
        if issues:
            with (self.runtime_dir / "recovery.jsonl").open("a", encoding="utf-8") as handle:
                for issue in issues:
                    handle.write(json.dumps(issue, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return issues

    def verify_chunks(self, session_id: str) -> list[dict[str, str]]:
        """Check registered final chunks without modifying or deleting evidence."""
        issues: list[dict[str, str]] = []
        with self._lock:
            session_path = Path(self.connection.execute(
                "SELECT path FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()[0])
            rows = self.connection.execute(
                "SELECT relative_path,file_size,sha256 FROM raw_chunks WHERE session_id=?", (session_id,)
            ).fetchall()
        for relative_path, file_size, sha256 in rows:
            path = session_path / relative_path
            if not path.is_file():
                issues.append({"path": str(path), "kind": "MISSING"})
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    digest.update(block)
            if path.stat().st_size != file_size or digest.hexdigest() != sha256:
                issues.append({"path": str(path), "kind": "CORRUPT"})
        return issues

    def create_session(self, product: dict | None = None, profile: dict | None = None,
                       provenance: dict | None = None) -> tuple[str, Path]:
        session_id = uuid4().hex
        path = self.runtime_dir / "sessions" / session_id
        for folder in ("raw", "events", "analysis"):
            (path / folder).mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat()
        provenance = provenance or {}
        for name, data in (
            ("manifest.json", {"session_id": session_id, "started_at": started_at, "status": SessionState.CREATED.value,
                               "provenance": provenance}),
            ("product_snapshot.json", product or {"status": "UNKNOWN"}),
            ("device_snapshot.json", {"devices": [], "provenance": provenance}),
            ("test_profile.json", profile or {"profile": "virtual-demo"}),
        ):
            (path / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO sessions(session_id,path,status,started_at,provenance_json) VALUES (?,?,?,?,?)",
                (session_id, str(path), SessionState.CREATED.value, started_at, json.dumps(provenance, sort_keys=True)),
            )
        return session_id, path

    def state(self, session_id: str) -> SessionState:
        with self._lock:
            row = self.connection.execute("SELECT status FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise StorageError(f"unknown session {session_id}")
        return SessionState(row[0])

    def transition(self, session_id: str, path: Path, new_state: SessionState) -> None:
        with self._lock, self.connection:
            old_state = self.state(session_id)
            if new_state not in TRANSITIONS.get(old_state, frozenset()):
                raise StorageError(f"invalid session transition {old_state} -> {new_state}")
            ended_at = datetime.now(timezone.utc).isoformat() if new_state in (
                SessionState.COMPLETE, SessionState.ABORTED, SessionState.INCOMPLETE, SessionState.FAILED
            ) else None
            self.connection.execute("UPDATE sessions SET status=?,ended_at=? WHERE session_id=?",
                                    (new_state.value, ended_at, session_id))
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = new_state.value
        if ended_at:
            manifest["ended_at"] = ended_at
        temp = manifest_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, manifest_path)

    def add_device(self, session_id: str, device_id: str, display_name: str, kind: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO devices VALUES (?,?,?) ON CONFLICT(device_id) DO UPDATE SET "
                "display_name=excluded.display_name,kind=excluded.kind", (device_id, display_name, kind))
            self.connection.execute("INSERT OR IGNORE INTO session_devices VALUES (?,?)", (session_id, device_id))
            row = self.connection.execute("SELECT path FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        snapshot_path = Path(row[0]) / "device_snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if not any(item["device_id"] == device_id for item in snapshot["devices"]):
            snapshot["devices"].append({"device_id": device_id, "display_name": display_name,
                                        "kind": kind, "is_simulation": kind == "SIMULATED"})
            temp = snapshot_path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temp, snapshot_path)

    def append_event(self, session_id: str, path: Path, event: Event) -> None:
        record = {"timestamp_utc": event.timestamp_utc.isoformat(), "name": event.name,
                  "device_id": event.device_id, "details": event.details}
        line = json.dumps(record, sort_keys=True, allow_nan=False) + "\n"
        with self._lock, self.connection:
            # Safety and storage workers can publish concurrently; serialize both sinks.
            with (path / "events" / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self.connection.execute(
                "INSERT INTO events(session_id,timestamp_utc,name,device_id,details_json) VALUES (?,?,?,?,?)",
                (session_id, record["timestamp_utc"], event.name, event.device_id, json.dumps(event.details, sort_keys=True)),
            )

    def add_chunk(self, session_id: str, device_id: str, relative_path: str, row_count: int, sha256: str,
                  min_ns: int, max_ns: int, file_size: int = 0, first_sequence: int = 0,
                  last_sequence: int = 0) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO raw_chunks(session_id,device_id,relative_path,row_count,sha256,min_monotonic_ns,"
                "max_monotonic_ns,file_size,first_sequence,last_sequence) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (session_id, device_id, relative_path, row_count, sha256, min_ns, max_ns, file_size,
                 first_sequence, last_sequence),
            )

    def finish_session(self, session_id: str, path: Path, status: str) -> None:
        self.transition(session_id, path, SessionState(status))

    def close(self) -> None:
        with self._lock:
            self.connection.close()
