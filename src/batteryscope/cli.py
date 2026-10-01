"""Entry point for the QML shell and deterministic headless demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from batteryscope.core.config import AppConfig
from batteryscope.core.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(prog="batteryscope")
    parser.add_argument("--headless-demo", action="store_true")
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime"))
    args = parser.parse_args()
    configure_logging()
    config = AppConfig(runtime_dir=args.runtime_dir)
    if args.headless_demo:
        from batteryscope.app.service import run_virtual_demo
        print(json.dumps(run_virtual_demo(config), indent=2, sort_keys=True))
        return 0
    from batteryscope.storage.session import SessionStore
    startup_store = SessionStore(config.runtime_dir)
    try:
        startup_store.recover_incomplete()
    finally:
        startup_store.close()
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from batteryscope.ui.bridge import BackendBridge

    application = QApplication([])
    bridge = BackendBridge(config)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", bridge)
    engine.load(Path(__file__).parent / "ui" / "qml" / "Main.qml")
    if not engine.rootObjects():
        return 1
    application.aboutToQuit.connect(bridge.shutdown)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
