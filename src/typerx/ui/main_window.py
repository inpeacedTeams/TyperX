from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from typerx.domain.models import TypingProfile
from typerx.domain.splitter import SmartSplitter, SplitPlan
from typerx.persistence.store import AppStore, new_template
from typerx.platform.windows import FocusChangedError, GlobalHotkeys
from typerx.services.typing_service import TypingCancelled, TypingService
from typerx.ui.theme import stylesheet

LOGGER = logging.getLogger(__name__)


class Bridge(QObject):
    start = Signal()
    stop = Signal()


class TypingWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, service: TypingService, plan: SplitPlan, profile: TypingProfile, target: int) -> None:
        super().__init__()
        self.service, self.plan, self.profile, self.target = service, plan, profile, target

    @Slot()
    def run(self) -> None:
        try:
            self.service.run(self.plan, self.profile, self.target, self.progress.emit)
            self.finished.emit(f"Готово: {len(self.plan.messages)} сообщений")
        except TypingCancelled:
            self.finished.emit("Остановлено")
        except FocusChangedError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            LOGGER.exception("Typing worker failed")
            detail = str(exc).strip() or exc.__class__.__name__
            self.failed.emit(f"Ошибка ввода: {detail}")


class MainWindow(QMainWindow):
    def __init__(self, store: AppStore) -> None:
        super().__init__()
        self.store, self.state = store, store.load()
        self.splitter, self.service, self.worker_thread = SmartSplitter(), None, None
        self._loading = True
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._persist)
        self.bridge = Bridge()
        self.bridge.start.connect(self._hotkey_start)
        self.bridge.stop.connect(self.stop_typing)
        self.hotkeys = GlobalHotkeys(self.bridge.start.emit, self.bridge.stop.emit)
        self.setWindowTitle("TyperX")
        self.resize(self.state.window_width, self.state.window_height)
        self.setMinimumSize(1080, 700)
        self.setStyleSheet(stylesheet())
        self._build_ui()
        self._populate_templates()
        self._load_profile(self.state.profile)
        self._loading = False
        self._select_initial()
        self.hotkeys.start()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        shell = QVBoxLayout(root)
        shell.setContentsMargins(24, 18, 24, 18)
        shell.setSpacing(16)
        shell.addWidget(self._topbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)
        splitter.addWidget(self._templates_panel())
        splitter.addWidget(self._editor_panel())
        splitter.addWidget(self._settings_panel())
        splitter.setSizes([240, 690, 320])
        shell.addWidget(splitter, 1)
        shell.addWidget(self._command_bar())
        self.setCentralWidget(root)

    def _topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(12)
        mark = QLabel("TX")
        mark.setObjectName("brandMark")
        mark.setFixedSize(38, 38)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("TyperX")
        brand.setObjectName("brand")
        claim = QLabel("натуральная печать, без облака")
        claim.setObjectName("muted")
        row.addWidget(mark)
        row.addWidget(brand)
        row.addWidget(claim)
        row.addStretch()
        shortcuts = QLabel("F8  старт    F9  стоп    F10  пауза")
        shortcuts.setObjectName("muted")
        row.addWidget(shortcuts)
        return bar

    def _templates_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("rail")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 18, 15, 15)
        layout.setSpacing(12)
        title = QLabel("БИБЛИОТЕКА")
        title.setObjectName("railEyebrow")
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setObjectName("railSearch")
        self.search.setPlaceholderText("Найти текст")
        self.search.textChanged.connect(self._filter_templates)
        layout.addWidget(self.search)
        self.templates = QListWidget()
        self.templates.setObjectName("templates")
        self.templates.currentItemChanged.connect(self._template_selected)
        layout.addWidget(self.templates, 1)
        hint = QLabel("Текст сохраняется автоматически")
        hint.setObjectName("railHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        add = QPushButton("+  Новый текст")
        add.setObjectName("railAction")
        add.clicked.connect(self._new_template)
        self.delete = QPushButton("Удалить")
        self.delete.setObjectName("danger")
        self.delete.clicked.connect(self._delete_template)
        layout.addWidget(add)
        layout.addWidget(self.delete)
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(310)
        return panel

    def _editor_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("workspace")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        page_title = QLabel("Рабочий текст")
        page_title.setObjectName("pageTitle")
        self.mode_description = QLabel("Собери текст и проверь, как он разобьётся на сообщения")
        self.mode_description.setObjectName("muted")
        title_box.addWidget(page_title)
        title_box.addWidget(self.mode_description)
        heading.addLayout(title_box)
        heading.addStretch()
        self.counter = QLabel("0 знаков")
        self.counter.setObjectName("muted")
        heading.addWidget(self.counter, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(heading)

        title_row = QHBoxLayout()
        self.title = QLineEdit()
        self.title.setObjectName("templateTitle")
        self.title.setPlaceholderText("Название текста")
        self.title.textChanged.connect(self._content_changed)
        self.save = QPushButton("Сохранить")
        self.save.clicked.connect(self._save_current)
        title_row.addWidget(self.title, 1)
        title_row.addWidget(self.save)
        layout.addLayout(title_row)

        self.editor = QTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setPlaceholderText("Вставь текст. TyperX сам выстроит паузы, ритм и отправку…")
        self.editor.textChanged.connect(self._content_changed)
        layout.addWidget(self.editor, 3)

        preview_header = QHBoxLayout()
        preview_title = QLabel("ПЛАН ОТПРАВКИ")
        preview_title.setObjectName("eyebrow")
        self.plan_meta = QLabel()
        self.plan_meta.setObjectName("muted")
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.plan_meta)
        layout.addLayout(preview_header)

        preview_strip = QFrame()
        preview_strip.setObjectName("previewStrip")
        preview_layout = QVBoxLayout(preview_strip)
        preview_layout.setContentsMargins(10, 5, 10, 5)
        self.preview = QListWidget()
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(135)
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_strip, 2)
        return panel

    def _settings_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("controls")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)
        title = QLabel("Режим и ритм")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        modes = QHBoxLayout()
        modes.setSpacing(6)
        self.message_mode = QPushButton("Сообщения")
        self.monkeytype_mode = QPushButton("Monkeytype")
        for button in (self.message_mode, self.monkeytype_mode):
            button.setObjectName("mode")
            button.setCheckable(True)
            modes.addWidget(button)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.message_mode)
        group.addButton(self.monkeytype_mode)
        self.message_mode.setChecked(True)
        self.monkeytype_mode.toggled.connect(self._mode_changed)
        outer.addLayout(modes)

        self.mode_hint = QLabel("Печать в активный чат с умной отправкой по сообщениям.")
        self.mode_hint.setObjectName("hint")
        self.mode_hint.setWordWrap(True)
        outer.addWidget(self.mode_hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 5, 4, 4)
        layout.setSpacing(12)
        layout.addWidget(self._eyebrow("СКОРОСТЬ"))
        self.wpm, self.wpm_value = self._slider(layout, "Темп", 25, 300)
        self.variation, self.variation_value = self._slider(layout, "Неровность ритма", 0, 55)
        self.typos, self.typos_value = self._slider(layout, "Частота опечаток", 0, 40)
        self.words, self.words_value = self._slider(layout, "Слов в сообщении", 1, 16)
        self.message_only_widgets = [self.words, self.words_value]

        layout.addSpacing(6)
        layout.addWidget(self._eyebrow("ПОВЕДЕНИЕ"))
        self.smart = self._checkbox(layout, "Делить текст по смыслу")
        self.fix_typos = self._checkbox(layout, "Добавлять опечатки")
        self.correct_typos = self._checkbox(layout, "Исправлять через Backspace")
        self.pause_marks = self._checkbox(layout, "Замедляться после пунктуации")
        self.keep_marks = self._checkbox(layout, "Сохранять пунктуацию")
        self.auto_123 = self._checkbox(layout, "Отвечать на запрос «123»")
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        panel.setMinimumWidth(285)
        panel.setMaximumWidth(370)
        return panel

    def _command_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("commandBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(10)
        dot = QLabel()
        dot.setObjectName("statusDot")
        self.status = QLabel("Готов к запуску")
        self.status.setObjectName("status")
        self.context = QLabel("Активное окно не выбрано")
        self.context.setObjectName("muted")
        self.start = QPushButton("Начать через 3 секунды")
        self.start.setObjectName("primary")
        self.start.setMinimumWidth(220)
        self.start.clicked.connect(self.start_countdown)
        self.stop = QPushButton("Остановить")
        self.stop.setObjectName("stop")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_typing)
        row.addWidget(dot)
        row.addWidget(self.status)
        row.addWidget(self.context)
        row.addStretch()
        row.addWidget(self.stop)
        row.addWidget(self.start)
        return bar

    @staticmethod
    def _eyebrow(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("eyebrow")
        return label

    def _checkbox(self, layout: QVBoxLayout, text: str) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.toggled.connect(self._settings_changed)
        layout.addWidget(checkbox)
        return checkbox

    def _slider(self, layout: QVBoxLayout, name: str, minimum: int, maximum: int):
        row = QHBoxLayout()
        label = QLabel(name)
        value = QLabel()
        value.setStyleSheet("color:#d24b35;font-weight:750")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.valueChanged.connect(self._settings_changed)
        layout.addLayout(row)
        layout.addWidget(slider)
        return slider, value

    def _mode_changed(self, monkeytype: bool) -> None:
        self.editor.setEnabled(not monkeytype)
        self.preview.setEnabled(not monkeytype)
        self.title.setEnabled(not monkeytype)
        self.save.setEnabled(not monkeytype)
        for widget in self.message_only_widgets:
            widget.setEnabled(not monkeytype)
        if monkeytype:
            self.mode_hint.setText("Открой тест с companion extension. Ошибки будут видны и исправлены, как у человека.")
            self.mode_description.setText("TyperX подхватит слова из открытого теста Monkeytype")
            self.start.setText("Подключить Monkeytype")
            self.plan_meta.setText("Текст придёт из браузера")
        else:
            self.mode_hint.setText("Печать в активный чат с умной отправкой по сообщениям.")
            self.mode_description.setText("Собери текст и проверь, как он разобьётся на сообщения")
            self.start.setText("Начать через 3 секунды")
            self._refresh_preview()
        self.start.setEnabled(self._can_start() and self.worker_thread is None)

    def _populate_templates(self) -> None:
        self.templates.clear()
        for template in self.state.templates:
            item = QListWidgetItem(template.title)
            item.setData(Qt.ItemDataRole.UserRole, template.id)
            self.templates.addItem(item)

    def _select_initial(self) -> None:
        for index in range(self.templates.count()):
            if self.templates.item(index).data(Qt.ItemDataRole.UserRole) == self.state.selected_template_id:
                self.templates.setCurrentRow(index)
                return
        if self.templates.count():
            self.templates.setCurrentRow(0)

    def _load_profile(self, profile: TypingProfile) -> None:
        self.wpm.setValue(profile.wpm)
        self.variation.setValue(profile.variation)
        self.typos.setValue(round(profile.typo_rate))
        self.words.setValue(profile.words_per_message)
        self.smart.setChecked(profile.smart_split)
        self.fix_typos.setChecked(profile.fix_typos)
        self.correct_typos.setChecked(profile.correct_typos)
        self.pause_marks.setChecked(profile.punctuation_pauses)
        self.keep_marks.setChecked(profile.keep_punctuation)
        self.auto_123.setChecked(profile.auto_123_challenge)
        self._refresh_labels()

    def _profile(self) -> TypingProfile:
        return TypingProfile(
            wpm=self.wpm.value(),
            variation=self.variation.value(),
            typo_rate=float(self.typos.value()),
            words_per_message=self.words.value(),
            smart_split=self.smart.isChecked(),
            fix_typos=self.fix_typos.isChecked(),
            correct_typos=self.correct_typos.isChecked(),
            punctuation_pauses=self.pause_marks.isChecked(),
            keep_punctuation=self.keep_marks.isChecked(),
            auto_123_challenge=self.auto_123.isChecked(),
        ).normalized()

    def _current_template(self):
        item = self.templates.currentItem()
        if not item:
            return None
        template_id = item.data(Qt.ItemDataRole.UserRole)
        return next((template for template in self.state.templates if template.id == template_id), None)

    def _template_selected(self, current, previous) -> None:
        del previous
        if current is None:
            return
        template = self._current_template()
        if template is None:
            return
        self._loading = True
        self.title.setText(template.title)
        self.editor.setPlainText(template.text)
        self._loading = False
        self.state.selected_template_id = template.id
        self.delete.setEnabled(not template.builtin)
        self._refresh_preview()
        self._schedule_save()

    def _content_changed(self) -> None:
        if self._loading:
            return
        self.counter.setText(f"{len(self.editor.toPlainText())} знаков")
        self._refresh_preview()

    def _settings_changed(self) -> None:
        if self._loading:
            return
        self._refresh_labels()
        if not self.monkeytype_mode.isChecked():
            self._refresh_preview()
        self._schedule_save()

    def _refresh_labels(self) -> None:
        self.wpm_value.setText(f"{self.wpm.value()} WPM")
        self.variation_value.setText(f"{self.variation.value()}%")
        self.typos_value.setText(f"{self.typos.value()}% слов")
        self.words_value.setText(f"≈ {self.words.value()}")

    def _refresh_preview(self) -> None:
        text = self.editor.toPlainText()
        self.preview.clear()
        plan = self.splitter.plan(text, self._profile(), seed=hash(text) & 0xFFFFFFFF)
        for index, message in enumerate(plan.messages, start=1):
            item = QListWidgetItem(f"{index:02}   {message}")
            item.setToolTip(message)
            self.preview.addItem(item)
        self.plan_meta.setText(f"{len(plan.messages)} сообщений · {plan.character_count} знаков")
        self.counter.setText(f"{len(text)} знаков")
        self.start.setEnabled(self._can_start() and self.worker_thread is None)

    def _can_start(self) -> bool:
        return self.monkeytype_mode.isChecked() or bool(self.editor.toPlainText().strip())

    def _new_template(self) -> None:
        template = new_template()
        self.state.templates.append(template)
        self._populate_templates()
        self.state.selected_template_id = template.id
        self._select_initial()
        self.title.selectAll()
        self.title.setFocus()
        self._schedule_save()

    def _save_current(self) -> None:
        template = self._current_template()
        if template is None:
            return
        if template.builtin:
            clone = new_template(self.title.text().strip() or template.title, self.editor.toPlainText())
            self.state.templates.append(clone)
            self.state.selected_template_id = clone.id
        else:
            template.title = self.title.text().strip()[:80] or "Без названия"
            template.text = self.editor.toPlainText()[:100_000]
        self._populate_templates()
        self._select_initial()
        self._persist()
        self.status.setText("Сохранено")

    def _delete_template(self) -> None:
        template = self._current_template()
        if template is None or template.builtin:
            return
        answer = QMessageBox.question(self, "Удалить текст?", f"«{template.title}» нельзя будет восстановить.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.state.templates.remove(template)
        self.state.selected_template_id = self.state.templates[0].id
        self._populate_templates()
        self._select_initial()
        self._persist()

    def _filter_templates(self, query: str) -> None:
        needle = query.casefold().strip()
        for index in range(self.templates.count()):
            item = self.templates.item(index)
            template_id = item.data(Qt.ItemDataRole.UserRole)
            template = next(entry for entry in self.state.templates if entry.id == template_id)
            item.setHidden(needle not in f"{template.title} {template.text}".casefold())

    def start_countdown(self) -> None:
        if self.worker_thread is not None:
            return
        self.showMinimized()
        self._countdown(3)

    def _countdown(self, remaining: int) -> None:
        if remaining <= 0:
            self._hotkey_start()
            return
        self.status.setText(f"Переключись в нужное окно: {remaining}")
        QTimer.singleShot(1000, lambda: self._countdown(remaining - 1))

    def _hotkey_start(self) -> None:
        pass

    def _typing_progress(self, current: int, total: int) -> None:
        self.status.setText(f"Печатаю {current} из {total}")

    def _typing_finished(self, message: str) -> None:
        self.status.setText(message)

    def _typing_failed(self, message: str) -> None:
        self.status.setText("Остановлено")
        self._error(message)

    def _thread_cleared(self) -> None:
        self.worker_thread = None
        self.service = None
        self.start.setEnabled(self._can_start())
        self.stop.setEnabled(False)

    def stop_typing(self) -> None:
        if self.service:
            self.service.cancel()

    def _error(self, text: str) -> None:
        self.showNormal()
        QMessageBox.warning(self, "TyperX", text)

    def _schedule_save(self) -> None:
        if not self._loading:
            self._save_timer.start(350)

    def _persist(self) -> None:
        self.state.profile = self._profile()
        self.state.window_width = self.width()
        self.state.window_height = self.height()
        try:
            self.store.save(self.state)
        except OSError:
            LOGGER.exception("Could not persist state")
            self.status.setText("Настройки не сохранены")

    def closeEvent(self, event) -> None:
        self.stop_typing()
        self.hotkeys.close()
        self._persist()
        super().closeEvent(event)
