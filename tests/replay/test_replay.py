import hashlib
from datetime import UTC, datetime

import pytest

from batteryscope.acquisition.engine import AcquisitionEngine
from batteryscope.core.config import AppConfig
from batteryscope.core.errors import ReplayError
from batteryscope.core.events import EventBus
from batteryscope.core.models import QualityFlag
from batteryscope.devices.replay import ReplayDevice
from batteryscope.devices.virtual.devices import VirtualC2
from batteryscope.storage.chunks import ChunkWriter
from batteryscope.storage.session import SessionStore


def test_parquet_replay_through_acquisition(tmp_path) -> None:
    store = SessionStore(tmp_path)
    first_id, first_path = store.create_session()
    c2 = VirtualC2()
    c2.connect()
    source = ChunkWriter(store, first_id, first_path).write("virtual:c2", list(c2.samples(3)))
    second_id, second_path = store.create_session()
    replay = ReplayDevice(source)
    replay.connect()
    bus = EventBus()
    acquisition = AcquisitionEngine(AppConfig(runtime_dir=tmp_path, chunk_max_rows=2),
                                    ChunkWriter(store, second_id, second_path), bus)
    samples = list(replay.samples(3))
    for sample in samples:
        acquisition.submit(sample)
    acquisition.close()
    assert all(QualityFlag.REPLAYED in sample.quality_flags for sample in samples)
    assert [sample.extras["original_sequence"] for sample in samples] == [1, 2, 3]
    assert [sample.extras["replay_sequence"] for sample in samples] == [1, 2, 3]
    assert len(list((second_path / "raw").glob("*.parquet"))) == 2
    replay.disconnect()
    store.close()


def test_replay_preserves_original_timing_and_verifies_chunk_hash(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session_id, path = store.create_session()
    c2 = VirtualC2()
    c2.connect()
    source = ChunkWriter(store, session_id, path).write("virtual:c2", list(c2.samples(2)))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ticks = iter((1001, 1002))
    replay = ReplayDevice(source, clock=lambda: (next(ticks), datetime(2026, 1, 1, tzinfo=UTC)),
                          expected_sha256=digest)
    replay.connect()
    samples = list(replay.samples(2))
    assert [sample.sequence for sample in samples] == [1, 2]
    assert [sample.extras["replay_ingest_timestamp_monotonic_ns"] for sample in samples] == [1001, 1002]
    assert [sample.extras["original_sequence"] for sample in samples] == [1, 2]
    assert all(sample.extras["original_timestamp_monotonic_ns"] != sample.timestamp_monotonic_ns for sample in samples)
    replay.disconnect()
    with pytest.raises(ReplayError):
        ReplayDevice(source, expected_sha256="0" * 64).connect()
    store.close()


def test_same_source_and_clock_replays_identical_measurement_values(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session_id, path = store.create_session()
    c2 = VirtualC2(scenario="voltage_sag", seed=381992,
                   clock=lambda: (42, datetime(2026, 1, 1, tzinfo=UTC)))
    c2.connect()
    source = ChunkWriter(store, session_id, path).write("virtual:c2", list(c2.samples(3)))

    def values() -> list[tuple[int, float, float, float, int]]:
        replay = ReplayDevice(source, clock=lambda: (99, datetime(2026, 1, 2, tzinfo=UTC)))
        replay.connect()
        rows = [(item.extras["original_sequence"], item.voltage_v, item.current_a,
                 item.power_w, item.extras["original_timestamp_monotonic_ns"])
                for item in replay.samples(3)]
        replay.disconnect()
        return rows

    assert values() == values()
    store.close()
