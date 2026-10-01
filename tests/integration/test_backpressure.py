from threading import Event as ThreadEvent

import pytest

from batteryscope.acquisition.engine import AcquisitionEngine, BackpressureExceeded
from batteryscope.core.config import AppConfig, BackpressurePolicy
from batteryscope.core.events import EventBus
from batteryscope.devices.virtual.devices import VirtualC2
from batteryscope.storage.chunks import ChunkWriter
from batteryscope.storage.session import SessionStore


def test_fail_safe_overflow_emits_event_without_silent_drop(tmp_path) -> None:
    entered = ThreadEvent()
    release = ThreadEvent()
    events = []

    class SlowWriter:
        def write(self, device_id, samples):
            entered.set()
            assert release.wait(5)

    bus = EventBus()
    bus.subscribe("*", events.append)
    config = AppConfig(runtime_dir=tmp_path, acquisition_queue_limit=16, chunk_max_rows=1,
                       queue_full_timeout_seconds=0.02, backpressure_policy=BackpressurePolicy.FAIL_SAFE)
    acquisition = AcquisitionEngine(config, SlowWriter(), bus)
    c2 = VirtualC2()
    c2.connect()
    try:
        acquisition.submit(next(iter(c2.samples(1))))
        assert entered.wait(2)
        for sample in c2.samples(16):
            acquisition.submit(sample)
        with pytest.raises(BackpressureExceeded):
            acquisition.submit(next(iter(c2.samples(1))))
        assert any(event.name == "BackpressureOverflow" for event in events)
    finally:
        release.set()
        acquisition.close()


def test_sequence_gap_records_missing_count(tmp_path) -> None:
    store = SessionStore(tmp_path)
    session_id, path = store.create_session()
    events = []
    bus = EventBus()
    bus.subscribe("*", events.append)
    acquisition = AcquisitionEngine(AppConfig(runtime_dir=tmp_path), ChunkWriter(store, session_id, path), bus)
    c2 = VirtualC2(scenario="data_gap")
    c2.connect()
    for sample in c2.samples(3):
        acquisition.submit(sample)
    acquisition.close()
    gaps = [event for event in events if event.name == "DataGapDetected" and "missing_count" in event.details]
    assert len(gaps) == 1
    assert gaps[0].details == {"missing_count": 1, "expected_sequence": 3, "actual_sequence": 4}
    store.close()
