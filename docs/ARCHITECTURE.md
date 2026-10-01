# Work Order 01 architecture

## Boundaries

QML calls `BackendBridge`, which starts an application worker. `app.service` owns session lifecycle and invokes the device manager, deterministic safety gate, acquisition, and storage. Device drivers depend on core models only; they never call SQLite. UI code neither imports a physical driver nor performs serial/USB I/O, SQL, Parquet, or DuckDB work. Optional search, analysis, intelligence, and reports are reserved package boundaries for later work.

## Device abstraction and plugin model

`IDevice`, `IMeter`, `ILoad`, `IPDAnalyzer`, `ITemperatureSensor`, `ISafetyControllable`, and `IReplayDevice` define narrow contracts. A plugin registry validates manifest capabilities against instantiated driver capabilities and requires an emergency-stop implementation when advertised. The registry passes no mutable Core object to drivers. Test planning must inspect capability names, never concrete model names. Physical IDs use `physical:`, simulation uses `virtual:`, replay uses `replay:`.

`VerifiedValue` carries value, unit, verification status, source kind, source, and verification time. `SIMULATED/TEST_FIXTURE` provenance is never a physical verified limit. Automatic physical control requires all voltage/current/power limits verified from physical documentation; unknown is deny even for a 1 W request. Physical write methods raise `NotVerifiedProtocolError` pending protocol evidence.

## Data path and pressure

Driver → bounded acquisition queue → per-device batch → Arrow table → ZSTD Parquet chunk → SQLite registration. UI receives only aggregate status signals. Config exposes chunk row/time bounds and `BLOCK`, `SPILL`, `FAIL_SAFE` pressure policy; the initial disk-spill interface is reserved, so its overflow raises. Overflow publishes `BackpressureOverflow`, and duplicate rejection publishes `SampleDropped`. A nonrecoverable pressure error triggers safe-state request before session teardown. Sequence gaps include expected/actual and missing count; timestamp gaps use configured expected interval.

## Storage and lifecycle

SQLite has `schema_info`, `sessions`, `devices`, `session_devices`, `events`, `raw_chunks`, and `app_versions`. Migration registry supports schema 1 → 2 → 3; schema 3 scopes raw chunk path uniqueness to a session. Lifecycle: `CREATED → RUNNING → STOPPING → COMPLETE | ABORTED | INCOMPLETE | FAILED`. The virtual emergency demo is `ABORTED`; an interrupted RUNNING/STOPPING session becomes `INCOMPLETE` at startup. `FAILED` denotes an internal processing failure. Metadata transactions use SQLite context managers.

Each chunk is written to `.tmp`, flushed/fsynced and closed, hashed, atomically replaced into its final path, then registered in SQLite with row count, file size, first/last sequence, first/last monotonic timestamp, and SHA-256. A crash between replace and DB registration leaves an orphan file. Startup recovery records interrupted, temporary, orphan, and manifest-mismatch artifacts in `recovery.jsonl` without deleting raw files. `verify_chunks` streams registered bytes to check size/hash.

## Safety boundary and shutdown

Emergency stop phases are `REQUESTED`, `ACKNOWLEDGED`, `VERIFIED_OFF`, `FAILED`. The control method runs before event dispatch, logging, DB writes, or queue draining. The UI signals `EmergencyStopChannel`; its dedicated safety worker invokes the stop while the acquisition/storage path runs separately. A failed event sink leaves an in-memory pending event and does not change the stop result. Virtual EBD verifies SAFE and zero setpoints; selecting CC/CP alone leaves the load disabled until `load_on()`. Physical drivers do not claim verified-off. Repeated virtual stops return `already_safe`. Normal shutdown stops accepting actions, requests safe state, stops acquisition, drains queues, finalizes chunks and session, closes DB, then exits UI. A hardware fail-open interlock is future work.

## Execution context

| Component | Execution context |
| --- | --- |
| QML/UI and Qt heartbeat | Main thread |
| Emergency-stop request | Main thread event signal only |
| Emergency-stop actuation | Dedicated `batteryscope-safety` thread |
| Virtual device reader and application orchestration | `DemoWorker` QThread; headless CLI caller |
| Acquisition submit and event dispatch | Application worker, synchronous |
| Parquet writer | Dedicated `batteryscope-storage` thread |
| DuckDB query | Dedicated `batteryscope-duckdb` executor thread |
| SQLite metadata | Serialized with `RLock`; event subscriber executes in publisher thread |

The event bus is synchronous and deliberately small. Events are for module decoupling, not an event-sourcing authority. Persistent event subscribers currently execute on the publisher thread and may delay routine acquisition; the dedicated safety lane performs load-off before publishing its event. Replay `MAX_SPEED` preserves original sequence/timestamp in extras and assigns new ingest sequence/timestamp. Simulator scenario and seed are written in session/device snapshots. The built-in scenarios are deterministic; any later randomness must use the persisted seed. `tools/benchmark_pipeline.py` records separate performance baselines without adding timing assertions to normal tests.
