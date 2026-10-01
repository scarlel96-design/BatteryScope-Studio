"""Load the minimal QML shell and check a live Qt heartbeat without backend I/O."""

from __future__ import annotations

import os
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication


class StubBackend(QObject):
    statusChanged = Signal()

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return "Session Idle"

    @Slot()
    def startSimulation(self) -> None:
        return None

    @Slot()
    def emergencyStop(self) -> None:
        return None


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([])
    engine = QQmlApplicationEngine()
    backend = StubBackend()
    engine.rootContext().setContextProperty("backend", backend)
    qml = Path(__file__).resolve().parents[1] / "src" / "batteryscope" / "ui" / "qml" / "Main.qml"
    engine.load(qml)
    assert len(engine.rootObjects()) == 1
    ticks: list[float] = []
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(monotonic()))
    heartbeat.start()
    QTimer.singleShot(120, app.quit)
    app.exec()
    assert len(ticks) >= 2
    print(f"QML shell PASS: roots={len(engine.rootObjects())}, heartbeat_ticks={len(ticks)}")


if __name__ == "__main__":
    main()
