from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout

from typerx.domain.models import TypingProfile
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
        self.status.setText("Готов · F8 старт · F9 стоп · F10 пауза")
        self.winId()
        exclude_process_windows_from_capture()
        self._capture_privacy_timer = QTimer(self)
        self._capture_privacy_timer.setInterval(250)
        self._capture_privacy_timer.timeout.connect(exclude_process_windows_from_capture)
        self._capture_privacy_timer.start()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, exclude_process_windows_from_capture)

    def _build_extra_settings(self, layout: QVBoxLayout) -> None:
        layout.addSpacing(6)
        layout.addWidget(self._eyebrow("ДЛИНА СООБЩЕНИЯ"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Слов в сообщении"))
        row.addStretch()
        self.words_value = QLabel()
        self.words_value.setObjectName("value")
        row.addWidget(self.words_value)
        self.words = QSlider(Qt.Orientation.Horizontal)
        self.words.setRange(1, 16)
        self.words.setToolTip("TyperX стремится к этой длине, иногда отклоняясь на одно слово")
        self.words.valueChanged.connect(self._settings_changed)
        layout.addLayout(row)
        layout.addWidget(self.words)

        layout.addSpacing(6)
        layout.addWidget(self._eyebrow("РЕЖИМ"))
        self.correct_typos = QCheckBox("Исправлять через Backspace")
        self.correct_typos.setToolTip("Выключи, чтобы оставлять часть опечаток в сообщениях")
        self.correct_typos.toggled.connect(self._settings_changed)
        self.auto_123 = QCheckBox("Автоответ на запрос 123")
        self.auto_123.toggled.connect(self._settings_changed)
        self.monkeytype_mode = QCheckBox("Monkeytype автотайп")
        self.monkeytype_mode.setToolTip("Открой practice/custom тест с companion extension и нажми F8")
        self.monkeytype_mode.toggled.connect(self._monkeytype_toggled)
        layout.addWidget(self.correct_typos)
        layout.addWidget(self.auto_123)
        layout.addWidget(self.monkeytype_mode)

    def _monkeytype_toggled(self, enabled: bool) -> None:
        if not hasattr(self, "start"):
            return
        if enabled:
            self.start.setText("Подключить Monkeytype")
            self.status.setText("Monkeytype: открой тест и нажми F8")
        else:
            self.start.setText("Начать через 3 секунды")
            self.status.setText("Готов · F8 старт · F9 стоп · F10 пауза")
        self._schedule_save()

    def _load_profile(self, profile: TypingProfile) -> None:
        super()._load_profile(profile)
        self.words.setValue(profile.words_per_message)
        self.correct_typos.setChecked(profile.correct_typos)
        self.auto_123.setChecked(profile.auto_123_challenge)
        self._refresh_labels()

    def _profile(self) -> TypingProfile:
        profile = super()._profile()
        profile.words_per_message = self.words.value()
        profile.correct_typos = self.correct_typos.isChecked()
        profile.auto_123_challenge = self.auto_123.isChecked()
        return profile.normalized()

    def _refresh_labels(self) -> None:
        super()._refresh_labels()
        if hasattr(self, "words_value"):
            self.words_value.setText(f"≈ {self.words.value()}")

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
            status = "Жду слова от Monkeytype extension…"
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

    @Slot()
    def _toggle_pause(self) -> None:
        if self.service is None:
            self.status.setText("Сначала запусти ввод · F8")
            return
        state = self.service.toggle_pause()
        if state == "resumed":
            self.status.setText("Продолжаю со следующего слова · F10 пауза")
        else:
            self.status.setText("Останавливаюсь после текущего слова…")

    @Slot()
    def _thread_cleared(self) -> None:
        self.worker = None
        super()._thread_cleared()

    def closeEvent(self, event) -> None:
        self.pause_hotkey.close()
        super().closeEvent(event)
