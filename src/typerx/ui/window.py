from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from typerx.domain.models import TypingProfile
from typerx.persistence.store import AppStore
from typerx.platform.capture_privacy import exclude_process_windows_from_capture
from typerx.platform.pause_hotkey import PauseHotkey
from typerx.platform.windows import WindowsInput
from typerx.services.monkeytype_service import MonkeytypeService
from typerx.services.typing_service import TypingService
from typerx.ui.main_window import MainWindow as MainWindowView
from typerx.ui.main_window import TypingWorker
from typerx.ui.monkeytype_options_page import MonkeytypeOptionsPage


class MainWindow(MainWindowView):
    pause_requested = Signal()

    def __init__(self, store: AppStore) -> None:
        self.worker: TypingWorker | None = None
        super().__init__(store)
        self._install_page_shell()
        self.pause_requested.connect(self._toggle_pause)
        self.pause_hotkey = PauseHotkey(self.pause_requested.emit)
        self.pause_hotkey.start()
        self.status.setText("Готов · F8 старт · F9 стоп · F10 пауза")
        self.winId()
        exclude_process_windows_from_capture()
        self._capture_privacy_timer = QTimer(self)
        self._capture_privacy_timer.setInterval(250)
        self._capture_privacy_timer.timeout.connect(exclude_process_windows_from_capture)
        self._capture_privacy_timer.start()

    def _install_page_shell(self) -> None:
        messages_page = self.takeCentralWidget()
        shell = QWidget()
        shell.setObjectName("pageShell")
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav = QFrame()
        nav.setObjectName("sideNav")
        nav.setFixedWidth(184)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(14, 18, 14, 16)
        nav_layout.setSpacing(8)
        brand = QLabel("TyperX")
        brand.setObjectName("navBrand")
        caption = QLabel("typing studio")
        caption.setObjectName("muted")
        nav_layout.addWidget(brand)
        nav_layout.addWidget(caption)
        nav_layout.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.messages_nav = self._nav_button("Сообщения", 0)
        self.monkeytype_nav = self._nav_button("Monkeytype", 1)
        nav_layout.addWidget(self.messages_nav)
        nav_layout.addWidget(self.monkeytype_nav)
        nav_layout.addStretch()
        safety = QLabel("Локально\nБез облака")
        safety.setObjectName("navFoot")
        nav_layout.addWidget(safety)

        self.pages = QStackedWidget()
        self.pages.addWidget(messages_page)
        self.monkeytype_page = MonkeytypeOptionsPage(self.state.profile)
        self.monkeytype_page.start_requested.connect(self._start_monkeytype)
        self.monkeytype_page.stop_requested.connect(self.stop_typing)
        self.monkeytype_page.settings_changed.connect(self._schedule_save)
        self.pages.addWidget(self.monkeytype_page)
        self.pages.currentChanged.connect(self._page_changed)
        self.messages_nav.setChecked(True)

        layout.addWidget(nav)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)

    def _nav_button(self, text: str, index: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setMinimumHeight(44)
        button.clicked.connect(lambda checked=False, page=index: self.pages.setCurrentIndex(page))
        self.nav_group.addButton(button, index)
        return button

    def _page_changed(self, index: int) -> None:
        button = self.nav_group.button(index)
        if button is not None:
            button.setChecked(True)
        if index == 0:
            self.status.setText("Готов · F8 старт · F9 стоп · F10 пауза")
        else:
            self.monkeytype_page.idle()

    def _start_monkeytype(self) -> None:
        self.monkeytype_page.preparing()
        self.start_countdown()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, exclude_process_windows_from_capture)

    def _profile(self) -> TypingProfile:
        profile = super()._profile()
        if hasattr(self, "pages") and self.pages.currentIndex() == 1:
            return self.monkeytype_page.apply_to_profile(profile)
        if hasattr(self, "monkeytype_page"):
            profile.correct_typos = self.monkeytype_page.correct_typos.isChecked()
        return profile.normalized()

    @Slot()
    def _hotkey_start(self) -> None:
        if self.worker_thread is not None:
            return
        target = WindowsInput.foreground_window()
        own_window = int(self.winId())
        if not target or target == own_window:
            message = "Открой поле ввода и нажми F8"
            if hasattr(self, "pages") and self.pages.currentIndex() == 1:
                self.monkeytype_page.failed(message)
            self._error(message)
            return

        profile = self._profile()
        monkeytype_mode = hasattr(self, "pages") and self.pages.currentIndex() == 1
        if monkeytype_mode:
            plan = self.splitter.plan("monkeytype", profile, seed=1)
            self.service = MonkeytypeService()
            status = "Жду слова от Monkeytype extension…"
            self.monkeytype_page.waiting()
        else:
            plan = self.splitter.plan(self.editor.toPlainText(), profile, seed=None)
            if not plan.messages:
                self._error("В шаблоне нет текста для отправки")
                return
            self.service = TypingService()
            status = "Запускаю ввод…"

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

    @Slot(int, int)
    def _typing_progress(self, current: int, total: int) -> None:
        super()._typing_progress(current, total)
        if self.pages.currentIndex() == 1:
            self.monkeytype_page.update_progress(current, total)

    @Slot(str)
    def _typing_finished(self, message: str) -> None:
        super()._typing_finished(message)
        if self.pages.currentIndex() == 1:
            self.monkeytype_page.finished(message)

    @Slot(str)
    def _typing_failed(self, message: str) -> None:
        if self.pages.currentIndex() == 1:
            self.monkeytype_page.failed(message)
        super()._typing_failed(message)

    @Slot()
    def _toggle_pause(self) -> None:
        if self.service is None:
            if self.pages.currentIndex() == 1:
                self.monkeytype_page.connection.setText("Сначала запусти сессию")
            else:
                self.status.setText("Сначала запусти ввод · F8")
            return
        state = self.service.toggle_pause()
        if state == "resumed":
            text = "Продолжаю со следующего слова · F10 пауза"
        else:
            text = "Останавливаюсь после текущего слова…"
        self.status.setText(text)
        if self.pages.currentIndex() == 1:
            self.monkeytype_page.connection.setText(text)

    @Slot()
    def _thread_cleared(self) -> None:
        self.worker = None
        super()._thread_cleared()
        if self.pages.currentIndex() == 1:
            self.monkeytype_page.start.setEnabled(True)
            self.monkeytype_page.stop.setEnabled(False)

    def closeEvent(self, event) -> None:
        self.pause_hotkey.close()
        super().closeEvent(event)
