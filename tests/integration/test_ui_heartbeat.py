"""The QML event loop remains responsive while the worker writes and queries."""

from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from time import monotonic, sleep

from PySide6.QtCore import QCoreApplication, QTimer

from batteryscope.app.service import run_virtual_demo
from batteryscope.core.config import AppConfig, Environment


def test_ui_heartbeat_during_demo(tmp_path) -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    ticks: list[float] = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(monotonic()))
    timer.start()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_virtual_demo, AppConfig(environment=Environment.TEST, runtime_dir=tmp_path,
                                                         chunk_max_rows=8), 80)
        deadline = monotonic() + 20
        while not future.done() and monotonic() < deadline:
            app.processEvents()
            sleep(0.005)
        result = future.result(timeout=1)
    timer.stop()
    assert result["rows"] == 160
    assert len(ticks) >= 2
    assert max(b - a for a, b in pairwise(ticks)) < 0.25
