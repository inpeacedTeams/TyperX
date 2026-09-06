from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from typerx.persistence.store import AppStore


def _configure_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(data_dir / "typerx.log", encoding="utf-8")],
    )
    # Network libraries must not log chat text or authentication details.
    logging.getLogger("telethon").setLevel(logging.WARNING)


def run() -> int:
    QCoreApplication.setOrganizationName("TyperX")
    QCoreApplication.setApplicationName("TyperX")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    legacy = "--legacy" in sys.argv
    app = QApplication([arg for arg in sys.argv if arg != "--legacy"])
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable", 10))
    store = AppStore.default()
    _configure_logging(store.data_dir)
    if legacy:
        from typerx.ui.window import MainWindow
        window = MainWindow(store)
    else:
        from typerx.ui.web_window import WebWindow
        window = WebWindow(store)
    window.show()
    return app.exec()
