from __future__ import annotations

from PySide6.QtCore import QThread, Slot

from typerx.domain.splitter import SplitPlan
from typerx.persistence.store import AppStore
from typerx.platform.windows import WindowsInput
from typerx.services.typing_service import TypingService
from typerx.ui.main_window import MainWindow as MainWindowView
from typerx.ui.main_window import TypingWorker


class MainWindow(MainWindowView):
    """Owns background typing sessions for their complete Qt lifecycle.

    PySide wrappers are reference-counted independently from their C++ objects. Keeping the
    worker only in a local variable can destroy it before QThread emits ``started``, producing
    a silent no-op. This controller holds both objects until ``finished``.
    """

    def __init__(self, store: AppStore) -> None:
        self.worker: TypingWorker | None = None
        super().__init__(store)

    @Slot()
    def _hotkey_start(self) -> None:
        if self.worker_thread is not None:
            return

        target = WindowsInput.foreground_window()
        own_window = int(self.winId())
        if not target or target == own_window:
            self._error("Открой чат и поставь курсор в поле сообщения, затем нажми F8")
            return

        plan: SplitPlan = self.splitter.plan(
            self.editor.toPlainText(), self._profile(), seed=None
        )
        if not plan.messages:
            self._error("В шаблоне нет текста для отправки")
            return

        self.service = TypingService()
        self.worker_thread = QThread(self)
        self.worker = TypingWorker(
            self.service, plan, self._profile(), target
        )
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
        self.status.setText("Запускаю ввод…")
        self.worker_thread.start()

    @Slot()
    def _thread_cleared(self) -> None:
        self.worker = None
        super()._thread_cleared()
