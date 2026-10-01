"""Application orchestration over virtual devices and persistent raw data."""

from __future__ import annotations

from threading import Event as StopEvent
from time import perf_counter, sleep

import structlog

from batteryscope.acquisition.engine import AcquisitionEngine
from batteryscope.app.stop_channel import EmergencyStopChannel
from batteryscope.core.config import AppConfig
from batteryscope.core.events import Event, EventBus
from batteryscope.core.models import SourceKind
from batteryscope.devices.manager import DeviceManager
from batteryscope.devices.virtual.devices import VirtualEBD
from batteryscope.plugins.registry import built_in_registry
from batteryscope.safety.engine import LoadRequest, SafetyEngine
from batteryscope.safety.stop import StopPhase, StopResult
from batteryscope.storage.chunks import ChunkWriter
from batteryscope.storage.query import DuckDBWorker
from batteryscope.storage.session import SessionState, SessionStore


def run_virtual_demo(config: AppConfig, sample_count: int = 8, stop_event: StopEvent | None = None,
                     scenario: str = "normal", seed: int = 0,
                     stop_channel: EmergencyStopChannel | None = None) -> dict[str, object]:
    """Exercise virtual discovery, safety stop, Arrow/Parquet, SQLite, and DuckDB."""
    start = perf_counter()
    log = structlog.get_logger()
    store = SessionStore(config.runtime_dir)
    recovery_issues = store.recover_incomplete()
    provenance = {"is_simulation": True, "simulator_version": VirtualEBD.simulator_version,
                  "scenario": scenario, "seed": seed, "fault_injected": scenario != "normal"}
    session_id, path = store.create_session(provenance=provenance)
    bus = EventBus()
    bus.subscribe("*", lambda event: store.append_event(session_id, path, event))
    manager = DeviceManager(built_in_registry(), bus)
    safety = SafetyEngine(bus)
    acquisition: AcquisitionEngine | None = None
    chunk_writer: ChunkWriter | None = None
    ebd: VirtualEBD | None = None
    stop_result: StopResult | None = None
    final_state = SessionState.FAILED
    failure: Exception | None = None
    samples_generated = 0
    try:
        identities = manager.discover()
        c2 = manager.connect("virtual:c2")
        ebd = manager.connect("virtual:ebd")
        c2.scenario, c2.seed = scenario, seed
        ebd.scenario, ebd.seed = scenario, seed
        for identity in identities:
            store.add_device(session_id, identity.device_id, identity.display_name, identity.kind.value)
        store.transition(session_id, path, SessionState.RUNNING)
        bus.publish(Event("SessionStarted", details={"session_id": session_id, "provenance": provenance}))
        chunk_writer = ChunkWriter(store, session_id, path)
        acquisition = AcquisitionEngine(config, chunk_writer, bus)
        request = LoadRequest(mode="CC", current_a=2.0, power_w=40.0, voltage_v=20.0)
        safety.validate_device_state(ebd.connected, ebd.get_status())
        safety.validate_requested_load(request, ebd.get_capabilities(), SourceKind.SIMULATED)
        if not (stop_event and stop_event.is_set()):
            ebd.set_constant_current(request.current_a)
            ebd.load_on()
            if stop_channel is not None:
                stop_channel.arm(ebd, safety, "virtual:ebd")
            bus.publish(Event("LoadStateChanged", "virtual:ebd", {"state": ebd.get_status()}))
        for _ in range(sample_count):
            if stop_event and stop_event.is_set():
                break
            for sample in c2.samples(1):
                samples_generated += 1
                acquisition.submit(sample)
            for sample in ebd.samples(1):
                samples_generated += 1
                acquisition.submit(sample)
            if stop_event:
                sleep(config.sample_interval_seconds)
        # The demo intentionally exercises the emergency path; that is an ABORTED session.
        stop_result = stop_channel.finish() if stop_channel is not None else None
        if stop_result is None:
            stop_result = safety.emergency_stop(ebd, "virtual:ebd")
        final_state = SessionState.ABORTED if stop_result.phase == StopPhase.VERIFIED_OFF else SessionState.FAILED
    except Exception as error:  # noqa: BLE001 - safety stop must run for any application failure
        failure = error
        if ebd is not None:
            stop_result = stop_channel.finish() if stop_channel is not None else None
            if stop_result is None:
                stop_result = safety.emergency_stop(ebd, "virtual:ebd")
        final_state = SessionState.ABORTED if isinstance(error, ConnectionError) and stop_result and stop_result.phase == StopPhase.VERIFIED_OFF else SessionState.FAILED
        log.error("session.failed", error_type=type(error).__name__, message=str(error))
    finally:
        # Load safe state always precedes queue drain, chunk finalization, and DB updates.
        if ebd is not None and (stop_result is None or stop_result.phase != StopPhase.VERIFIED_OFF):
            pending_stop = stop_channel.finish() if stop_channel is not None else None
            stop_result = pending_stop or safety.emergency_stop(ebd, "virtual:ebd")
        if store.state(session_id) == SessionState.RUNNING:
            store.transition(session_id, path, SessionState.STOPPING)
        if acquisition is not None:
            try:
                acquisition.close()
            except Exception as error:  # noqa: BLE001 - continue ordered shutdown
                failure = failure or error
                final_state = SessionState.FAILED
        try:
            bus.publish(Event("SessionStopped", details={"status": final_state.value}))
        except Exception as error:  # noqa: BLE001 - continue ordered shutdown
            failure = failure or error
            final_state = SessionState.FAILED
        try:
            manager.disconnect_all()
        except Exception as error:  # noqa: BLE001 - continue ordered shutdown
            failure = failure or error
            final_state = SessionState.FAILED
        try:
            current = store.state(session_id)
            if current == SessionState.STOPPING:
                store.transition(session_id, path, final_state)
            elif current == SessionState.CREATED:
                store.transition(session_id, path, SessionState.FAILED)
            event_count = store.connection.execute(
                "SELECT count(*) FROM events WHERE session_id=?", (session_id,)
            ).fetchone()[0]
        except Exception as error:  # noqa: BLE001 - preserve failure while closing store
            failure = failure or error
            event_count = 0
        finally:
            store.close()
    if failure is not None:
        raise failure
    raw_files = sorted((path / "raw").glob("*.parquet"))
    if not raw_files:
        raise RuntimeError("demo produced no Parquet chunks")
    query = DuckDBWorker()
    try:
        stats = query.summarize(path / "raw" / "*.parquet").result()
    finally:
        query.close()
    log.info("session.stopped", session_id=session_id, rows=stats["rows"], state=final_state.value)
    return {"session_id": session_id, "session_path": str(path), "status": final_state.value,
            "devices": [identity.device_id for identity in identities], "raw_chunks": len(raw_files),
            "events": event_count, "load_state": ebd.state.value,
            "session_state": final_state.value, "devices_connected": [identity.device_id for identity in identities],
            "samples_generated": samples_generated, "samples_written": stats["rows"],
            "chunks_created": len(raw_files), "events_written": event_count,
            "emergency_stop_state": stop_result.phase.value if stop_result else "FAILED",
            "duckdb_row_count": stats["rows"],
            "load_enabled": ebd.load_enabled,
            "emergency_stop_phase": stop_result.phase.value if stop_result else "FAILED",
            "queue_max_depth": acquisition.max_queue_depth if acquisition else 0,
            "chunk_write_bytes_per_second": (chunk_writer.bytes_written / chunk_writer.write_seconds
                                             if chunk_writer and chunk_writer.write_seconds else 0.0),
            "ingestion_samples_per_second": stats["rows"] / max(perf_counter() - start, 1e-9),
            "recovery_issues": len(recovery_issues), **stats}
