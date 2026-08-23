from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal, Slot
from PySide6.QtGui import QShowEvent

from typerx.persistence.store import AppStore
from typerx.platform.capture_privacy import exclude_process_windows_from_capture
from typerx.platform.pause_hotkey import PauseHotkey
from typerx.platform.windows import WindowsInput
from typerx.services.monkeytype_service import MonkeytypeService
from typerx.services.typing_service import TypingService
from typerx.ui.main_window import MainWindow as MainWindowView
from typerx.ui.main_window import TypingWorker


class MainWindow(MainWindowView):
    pause_requested = Signal()

    def __init__(self, store: AppStore) -> None:
        self.worker: TypingWorker | None = None
        super().__init__(store)
        self.pause_requested.connect(self._toggle_pause)
        self.pause_hotkey = PauseHotkey(self.pause_requested.emit)
        self.pause_hotkey.start()
        self.winId()
        exclude_process_windows_from_capture()
        self._capture_privacy_timer = QTimer(self)
        self._capture_privacy_timer.setInterval(250)
        self._capture_privacy_timer.timeout.connect(exclude_process_windows_from_capture)
        self._capture_privacy_timer.start()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, exclude_process_windows_from_capture)

    @Slot()
    def _hotkey_start(self) -> None:
        if self.worker_thread is not None:
            return
        target = WindowsInput.foreground_window()
        own_window = int(self.winId())
        if not target or target == own_window:
            self._error("Открой поле ввода и нажми F8")
            return

        profile = self._profile()
        if self.monkeytype_mode.isChecked():
            plan = self.splitter.plan("monkeytype", profile, seed=1)
            self.service = MonkeytypeService()
            status = "Жду тест от Monkeytype extension…"
            self.context.setText("Monkeytype · локальный мост")
        else:
            plan = self.splitter.plan(self.editor.toPlainText(), profile, seed=None)
            if not plan.messages:
                self._error("В тексте нечего печатать")
                return
            self.service = TypingService()
            status = "Запускаю ввод…"
            self.context.setText(f"{len(plan.messages)} сообщений")

        self.worker_thread = QThread(self)
        self.worker = TypingWorker(self.service, plan, profile, target)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._typing_progress)
        self.worker.finished.connect(self._typing_finished)
        self.worker.failed.connect(self._typing_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._thread_cleared)
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        self.status.setText(status)
        self.worker_thread.start()

    @Slot()
    def _toggle_pause(self) -> None:
        if self.service is None:
            self.status.setText("Сначала запусти ввод · F8")
            return
        state = self.service.toggle_pause()
        if state == "resumed":
            self.status.setText("Продолжаю со следующего слова")
        else:
            self.status.setText("Пауза после текущего слова…")

    @Slot()
    def _thread_cleared(self) -> None:
        self.worker = None
        self.context.setText("Активное окно не выбрано")
        super()._thread_cleared()

    def closeEvent(self, event) -> None:
        self.pause_hotkey.close()
        super().closeEvent(event)
