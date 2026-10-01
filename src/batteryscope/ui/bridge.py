"""Queued UI bridge: all persistence and simulation run on a worker thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Property, QThread, Signal, Slot

from batteryscope.app.service import run_virtual_demo
from batteryscope.app.stop_channel import EmergencyStopChannel
from batteryscope.core.config import AppConfig


class DemoWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, config: AppConfig, stop_channel: EmergencyStopChannel) -> None:
        super().__init__()
        self.config = config
        self.stop_channel = stop_channel

    def run(self) -> None:
        try:
            result = run_virtual_demo(self.config, sample_count=250, stop_event=self.stop_channel.requested,
                                      stop_channel=self.stop_channel)
            self.completed.emit(f"{result['status']} · {result['rows']} samples · {result['load_state']}")
        except Exception as error:
            self.failed.emit(f"Simulation failed: {type(error).__name__}: {error}")


class BackendBridge(QObject):
    statusChanged = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._status = "Session Idle"
        self._worker: DemoWorker | None = None
        self._stop_channel = EmergencyStopChannel()

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    def _set_status(self, value: str) -> None:
        self._status = value
        self.statusChanged.emit()

    @Slot()
    def startSimulation(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._stop_channel = EmergencyStopChannel()
        self._worker = DemoWorker(self.config, self._stop_channel)
        self._worker.completed.connect(self._set_status)
        self._worker.failed.connect(self._set_status)
        self._set_status("Simulation running · virtual devices connected")
        self._worker.start()

    @Slot()
    def emergencyStop(self) -> None:
        self._stop_channel.request()
        self._set_status("Emergency stop requested")

    def shutdown(self) -> None:
        self._stop_channel.request()
        if self._worker and self._worker.isRunning():
            self._worker.wait(10000)
