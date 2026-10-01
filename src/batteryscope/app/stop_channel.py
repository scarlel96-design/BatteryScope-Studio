"""Priority stop lane: UI signals it without performing device I/O."""

from __future__ import annotations

from threading import Event, Lock, Thread

from batteryscope.devices.base.contracts import ISafetyControllable
from batteryscope.safety.engine import SafetyEngine
from batteryscope.safety.stop import StopResult


class EmergencyStopChannel:
    def __init__(self) -> None:
        self.requested = Event()
        self._lock = Lock()
        self._control: ISafetyControllable | None = None
        self._engine: SafetyEngine | None = None
        self._device_id: str | None = None
        self._thread: Thread | None = None
        self._result: StopResult | None = None

    def arm(self, control: ISafetyControllable, engine: SafetyEngine, device_id: str) -> None:
        with self._lock:
            self._control, self._engine, self._device_id = control, engine, device_id
            if self.requested.is_set():
                self._start_locked()

    def request(self) -> None:
        # This path only sets an event and launches a dedicated safety worker.
        self.requested.set()
        with self._lock:
            self._start_locked()

    def _start_locked(self) -> None:
        if self._control is None or self._thread is not None:
            return
        self._thread = Thread(target=self._stop, name="batteryscope-safety", daemon=False)
        self._thread.start()

    def _stop(self) -> None:
        assert self._control is not None and self._engine is not None and self._device_id is not None
        self._result = self._engine.emergency_stop(self._control, self._device_id)

    def finish(self) -> StopResult | None:
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join()
        return self._result
