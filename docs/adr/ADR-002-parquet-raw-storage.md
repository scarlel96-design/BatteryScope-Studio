# ADR-002: Parquet raw storage

Status: Accepted. Canonical samples become Arrow tables and bounded ZSTD Parquet chunks. SQLite stores session metadata and chunk integrity fields, while DuckDB reads the raw files. This avoids millions of SQLite telemetry rows and allows independent replay. Atomic file finalization precedes DB registration; orphan scanning handles the crash window.
