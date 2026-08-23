from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from typerx.domain.models import TypingProfile


def estimate_seconds(characters: int, wpm: int, typo_rate: float) -> float:
    base = max(0, characters) / (max(1, wpm) * 5) * 60
    words = max(0, characters) / 5
    correction_time = words * max(0.0, typo_rate) / 100 * 0.35
    return base + correction_time


def format_duration(seconds: float) -> str:
    rounded = max(1, round(seconds))
    if rounded < 60:
        return f"≈ {rounded} сек"
    minutes, remainder = divmod(rounded, 60)
    return f"≈ {minutes} мин {remainder:02} сек"


class MonkeytypePage(QWidget):
    start_requested = Signal()
    stop_requested = Signal()
    settings_changed = Signal()

    def __init__(self, profile: TypingProfile) -> None:
        super().__init__()
        self._total = 0
        self._build_ui()
        self.load_profile(profile)
        self._refresh_forecast()

    def _build_ui(self) -> None:
        shell = QVBoxLayout(self)
        shell.setContentsMargins(28, 24, 28, 24)
        shell.setSpacing(18)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        eyebrow = QLabel("MONKEYTYPE LAB")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Автотайп без ощущения робота")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Открой practice или custom test. TyperX поймает текст и напечатает его живым ритмом.")
        subtitle.setObjectName("muted")
        self.connection = QLabel("Готов к подключению")
        self.connection.setObjectName("status")
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(self.connection, 0, Qt.AlignmentFlag.AlignTop)
        shell.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._session_panel(), 3)
        body.addWidget(self._controls_panel(), 2)
        shell.addLayout(body, 1)

    def _session_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("monkeyHero")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(14)

        label = QLabel("СЕССИЯ")
        label.setObjectName("eyebrow")
        self.session_title = QLabel("Monkeytype ждёт тебя")
        self.session_title.setObjectName("monkeyTitle")
        self.session_hint = QLabel("Нажми старт, затем за 3 секунды переключись в окно теста.")
        self.session_hint.setObjectName("muted")
        self.session_hint.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self.session_title)
        layout.addWidget(self.session_hint)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.speed_stat = self._stat("105", "WPM")
        self.typo_stat = self._stat("12%", "ОПЕЧАТКИ")
        self.time_stat = self._stat("≈ 29 сек", "50 СЛОВ")
        stats.addWidget(self.speed_stat)
        stats.addWidget(self.typo_stat)
        stats.addWidget(self.time_stat)
        layout.addLayout(stats)

        preview = QFrame()
        preview.setObjectName("typoPreview")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(14, 12, 14, 12)
        preview_layout.setSpacing(4)
        preview_label = QLabel("КАК ЭТО БУДЕТ ВЫГЛЯДЕТЬ")
        preview_label.setObjectName("eyebrow")
        self.preview_text = QLabel("natural  →  natiral  →  natural")
        self.preview_text.setObjectName("previewText")
        preview_note = QLabel("Ошибка появляется, короткая реакция, Backspace, правильная буква.")
        preview_note.setObjectName("muted")
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self.preview_text)
        preview_layout.addWidget(preview_note)
        layout.addWidget(preview)
        layout.addStretch()

        actions = QHBoxLayout()
        self.stop = QPushButton("Остановить")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_requested.emit)
        self.start = QPushButton("Подключить и начать")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.start_requested.emit)
        actions.addWidget(self.stop)
        actions.addStretch()
        actions.addWidget(self.start)
        layout.addLayout(actions)
        return panel

    def _controls_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("monkeyControls")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(12)
        title = QLabel("Характер печати")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        presets = QHBoxLayout()
        presets.setSpacing(7)
        for name, wpm, variation, typos in (
            ("Спокойно", 70, 18, 6),
            ("Живо", 105, 24, 12),
            ("Быстро", 155, 18, 8),
        ):
            button = QPushButton(name)
            button.setObjectName("preset")
            button.clicked.connect(
                lambda checked=False, values=(wpm, variation, typos): self._apply_preset(*values)
            )
            presets.addWidget(button)
        layout.addLayout(presets)

        self.wpm, self.wpm_value = self._slider(layout, "Скорость", 25, 300)
        self.variation, self.variation_value = self._slider(layout, "Живой разброс", 0, 55)
        self.typos, self.typos_value = self._slider(layout, "Частота опечаток", 0, 40)
        self.typos_enabled = QCheckBox("Показывать и исправлять опечатки")
        self.typos_enabled.toggled.connect(self._changed)
        layout.addWidget(self.typos_enabled)

        layout.addSpacing(4)
        checklist = QLabel("ПЕРЕД СТАРТОМ")
        checklist.setObjectName("eyebrow")
        layout.addWidget(checklist)
        for text in (
            "1  Interception driver установлен",
            "2  Companion extension включён",
            "3  Practice или custom test открыт",
        ):
            item = QLabel(text)
            item.setObjectName("checkItem")
            layout.addWidget(item)
        layout.addStretch()

        hotkeys = QLabel("F8 старт  ·  F9 стоп  ·  F10 пауза")
        hotkeys.setObjectName("note")
        hotkeys.setWordWrap(True)
        layout.addWidget(hotkeys)
        return panel

    @staticmethod
    def _stat(value: str, caption: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("miniStat")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(1)
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        caption_label = QLabel(caption)
        caption_label.setObjectName("eyebrow")
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        frame.value_label = value_label
        return frame

    def _slider(self, layout: QVBoxLayout, title: str, minimum: int, maximum: int):
        row = QHBoxLayout()
        row.addWidget(QLabel(title))
        row.addStretch()
        value = QLabel()
        value.setObjectName("value")
        row.addWidget(value)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.valueChanged.connect(self._changed)
        layout.addLayout(row)
        layout.addWidget(slider)
        return slider, value

    def _apply_preset(self, wpm: int, variation: int, typos: int) -> None:
        self.wpm.setValue(wpm)
        self.variation.setValue(variation)
        self.typos.setValue(typos)
        self.typos_enabled.setChecked(typos > 0)
        self._changed()

    def _changed(self) -> None:
        self._refresh_forecast()
        self.settings_changed.emit()

    def _refresh_forecast(self) -> None:
        rate = self.typos.value() if self.typos_enabled.isChecked() else 0
        self.wpm_value.setText(f"{self.wpm.value()} WPM")
        self.variation_value.setText(f"{self.variation.value()}%")
        self.typos_value.setText(f"{rate}% слов")
        self.speed_stat.value_label.setText(str(self.wpm.value()))
        self.typo_stat.value_label.setText(f"{rate}%")
        self.time_stat.value_label.setText(format_duration(estimate_seconds(250, self.wpm.value(), rate)))
        self.preview_text.setText(
            "natural  →  natiral  →  natural" if rate else "natural  →  natural"
        )

    def load_profile(self, profile: TypingProfile) -> None:
        self.wpm.setValue(profile.wpm)
        self.variation.setValue(profile.variation)
        self.typos.setValue(round(profile.typo_rate))
        self.typos_enabled.setChecked(profile.fix_typos and profile.typo_rate > 0)

    def apply_to_profile(self, profile: TypingProfile) -> TypingProfile:
        profile.wpm = self.wpm.value()
        profile.variation = self.variation.value()
        profile.typo_rate = float(self.typos.value() if self.typos_enabled.isChecked() else 0)
        profile.fix_typos = self.typos_enabled.isChecked()
        profile.correct_typos = True
        return profile.normalized()

    def preparing(self) -> None:
        self.connection.setText("Переключись в Monkeytype")
        self.session_title.setText("Старт через 3 секунды")
        self.session_hint.setText("Фокус должен остаться в поле теста. TyperX сам дождётся текста от extension.")
        self.start.setEnabled(False)
        self.stop.setEnabled(True)

    def waiting(self) -> None:
        self.connection.setText("Жду extension")
        self.session_title.setText("Слушаю Monkeytype…")
        self.session_hint.setText("Не закрывай тест. Как только extension пришлёт слова, печать начнётся.")
        self.start.setEnabled(False)
        self.stop.setEnabled(True)

    def update_progress(self, current: int, total: int) -> None:
        self._total = total
        percent = round(current / total * 100) if total else 0
        self.progress.setValue(percent)
        self.connection.setText("Печатаю")
        self.session_title.setText(f"{percent}% теста готово")
        remaining = max(0, total - current)
        rate = self.typos.value() if self.typos_enabled.isChecked() else 0
        self.session_hint.setText(
            f"Осталось {remaining} символов · {format_duration(estimate_seconds(remaining, self.wpm.value(), rate))}"
        )

    def finished(self, message: str) -> None:
        self.progress.setValue(100 if self._total else 0)
        self.connection.setText("Готово")
        self.session_title.setText("Сессия завершена")
        self.session_hint.setText(message)
        self.start.setEnabled(True)
        self.stop.setEnabled(False)

    def failed(self, message: str) -> None:
        self.connection.setText("Нужна проверка")
        self.session_title.setText("Не удалось запустить")
        self.session_hint.setText(message)
        self.start.setEnabled(True)
        self.stop.setEnabled(False)

    def idle(self) -> None:
        self.connection.setText("Готов к подключению")
        self.session_title.setText("Monkeytype ждёт тебя")
        self.session_hint.setText("Нажми старт, затем за 3 секунды переключись в окно теста.")
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
