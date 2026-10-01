"""Bounded ingestion, quality marking, and a dedicated storage writer thread."""

from __future__ import annotations

from collections import defaultdict
from queue import Full, Queue
from threading import Thread
from time import monotonic

from batteryscope.core.config import AppConfig, BackpressurePolicy
from batteryscope.core.events import Event, EventBus
from batteryscope.core.models import MeasurementSample, QualityFlag
from batteryscope.storage.chunks import ChunkWriter


class BackpressureExceeded(RuntimeError):
    pass


class AcquisitionEngine:
    def __init__(self, config: AppConfig, writer: ChunkWriter, bus: EventBus) -> None:
        self.config = config
        self.writer = writer
        self.bus = bus
        self.queue: Queue[MeasurementSample | None] = Queue(maxsize=config.acquisition_queue_limit)
        self.last_sequence: dict[str, int] = {}
        self.last_monotonic_ns: dict[str, int] = {}
        self.max_queue_depth = 0
        self.writer_error: BaseException | None = None
        self.warning_active = False
        self.thread = Thread(target=self._write_loop, name="batteryscope-storage", daemon=False)
        self.thread.start()

    def submit(self, sample: MeasurementSample) -> None:
        if self.writer_error:
            raise RuntimeError("storage writer failed") from self.writer_error
        previous = self.last_sequence.get(sample.source_device_id)
        if previous is not None:
            if sample.sequence == previous:
                self.bus.publish(Event("SampleDropped", sample.source_device_id,
                                       {"sequence": sample.sequence, "reason": "duplicate", "quality_flag": "DROPPED_SAMPLE"}))
                return
            if sample.sequence < previous:
                self.bus.publish(Event("OutOfOrderDetected", sample.source_device_id,
                                       {"sequence": sample.sequence, "previous": previous}))
                sample = sample.model_copy(update={"quality_flags": sample.quality_flags | {QualityFlag.OUT_OF_ORDER}})
            elif sample.sequence > previous + 1:
                self.bus.publish(Event("DataGapDetected", sample.source_device_id,
                                       {"missing_count": sample.sequence - previous - 1,
                                        "expected_sequence": previous + 1, "actual_sequence": sample.sequence}))
                sample = sample.model_copy(update={"quality_flags": sample.quality_flags | {QualityFlag.DATA_GAP}})
        previous_ns = self.last_monotonic_ns.get(sample.source_device_id)
        expected_ns = int(self.config.sample_interval_seconds * 1_000_000_000)
        if previous_ns is not None and sample.timestamp_monotonic_ns - previous_ns > expected_ns * self.config.timestamp_gap_factor:
            self.bus.publish(Event("DataGapDetected", sample.source_device_id,
                                   {"elapsed_ns": sample.timestamp_monotonic_ns - previous_ns,
                                    "expected_interval_ns": expected_ns, "reason": "timestamp"}))
            sample = sample.model_copy(update={"quality_flags": sample.quality_flags | {QualityFlag.DATA_GAP}})
        self.last_sequence[sample.source_device_id] = max(sample.sequence, previous or 0)
        self.last_monotonic_ns[sample.source_device_id] = sample.timestamp_monotonic_ns
        warning_at = int(self.config.acquisition_queue_limit * self.config.queue_warning_fraction)
        if self.queue.qsize() >= warning_at and not self.warning_active:
            self.warning_active = True
            self.bus.publish(Event("AcquisitionBackpressure", sample.source_device_id,
                                   {"queued": self.queue.qsize()}))
        while True:
            if self.writer_error:
                raise RuntimeError("storage writer failed") from self.writer_error
            try:
                self.queue.put(sample, timeout=self.config.queue_full_timeout_seconds)
                self.max_queue_depth = max(self.max_queue_depth, self.queue.qsize())
                break
            except Full as error:
                if self.config.backpressure_policy == BackpressurePolicy.BLOCK:
                    continue
                self.bus.publish(Event("BackpressureOverflow", sample.source_device_id,
                                       {"queued": self.queue.qsize(), "policy": self.config.backpressure_policy.value,
                                        "quality_flag": "BACKPRESSURE_OVERFLOW"}))
                if self.config.backpressure_policy == BackpressurePolicy.SPILL:
                    raise BackpressureExceeded("SPILL interface reserved; no disk spool configured") from error
                raise BackpressureExceeded("acquisition queue full") from error

    def _write_loop(self) -> None:
        batches: dict[str, list[MeasurementSample]] = defaultdict(list)
        first_at: dict[str, float] = {}
        try:
            while True:
                item = self.queue.get()
                try:
                    if item is None:
                        break
                    device_id = item.source_device_id
                    if not batches[device_id]:
                        first_at[device_id] = monotonic()
                    batches[device_id].append(item)
                    elapsed = monotonic() - first_at[device_id]
                    if len(batches[device_id]) >= self.config.chunk_max_rows or elapsed >= self.config.chunk_max_seconds:
                        self.writer.write(device_id, batches[device_id])
                        self.bus.publish(Event("RawChunkWritten", device_id, {"rows": len(batches[device_id])}))
                        batches[device_id] = []
                    if self.warning_active and self.queue.qsize() < self.config.acquisition_queue_limit // 2:
                        self.warning_active = False
                finally:
                    self.queue.task_done()
            for device_id, batch in batches.items():
                if batch:
                    self.writer.write(device_id, batch)
                    self.bus.publish(Event("RawChunkWritten", device_id, {"rows": len(batch)}))
        except BaseException as error:
            self.writer_error = error

    def close(self) -> None:
        if self.writer_error:
            raise RuntimeError("storage writer failed") from self.writer_error
        while True:
            if self.writer_error:
                raise RuntimeError("storage writer failed") from self.writer_error
            try:
                self.queue.put(None, timeout=self.config.queue_full_timeout_seconds)
                break
            except Full:
                continue
        self.thread.join()
        if self.writer_error:
            raise RuntimeError("storage writer failed") from self.writer_error
