"""Load real QML/bridge, activate both actions, and measure the UI heartbeat."""

from __future__ import annotations

import os
import sys
from itertools import pairwise
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QMetaObject, QObject, QTimer
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from batteryscope.core.config import AppConfig
from batteryscope.ui.bridge import BackendBridge


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([])
    engine = QQmlApplicationEngine()
    backend = BackendBridge(AppConfig(runtime_dir=Path("runtime/qml-validation"), chunk_max_rows=16))
    engine.rootContext().setContextProperty("backend", backend)
    qml = Path(__file__).resolve().parents[1] / "src" / "batteryscope" / "ui" / "qml" / "Main.qml"
    engine.load(qml)
    assert len(engine.rootObjects()) == 1
    root = engine.rootObjects()[0]
    start_button = root.findChild(QObject, "startSimulationButton")
    stop_button = root.findChild(QObject, "emergencyStopButton")
    assert start_button is not None and stop_button is not None
    ticks: list[float] = []
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(monotonic()))
    heartbeat.start()
    QTimer.singleShot(0, lambda: QMetaObject.invokeMethod(start_button, "clicked"))
    QTimer.singleShot(100, lambda: QMetaObject.invokeMethod(stop_button, "clicked"))
    def finish_if_done() -> None:
        worker = backend._worker
        if worker is not None and not worker.isRunning():
            app.quit()
    completion = QTimer()
    completion.setInterval(20)
    completion.timeout.connect(finish_if_done)
    completion.start()
    QTimer.singleShot(10000, app.quit)
    app.exec()
    completion.stop()
    backend.shutdown()
    assert len(ticks) >= 2
    assert backend._worker is not None and not backend._worker.isRunning()
    assert "ABORTED" in backend.status and "SAFE" in backend.status
    max_pause_ms = max(b - a for a, b in pairwise(ticks)) * 1000
    assert max_pause_ms < 250
    assert not any(name.startswith(("PySide6.QtGraphs", "PySide6.QtCharts")) for name in sys.modules)
    print(f"QML shell PASS: roots={len(engine.rootObjects())}, actions=start/stop, "
          f"status={backend.status}, heartbeat_ticks={len(ticks)}, max_pause_ms={max_pause_ms:.1f}, "
          "QtGraphs_loaded=false")


if __name__ == "__main__":
    main()
