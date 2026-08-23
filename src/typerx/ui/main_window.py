from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
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
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from typerx.domain.models import TextTemplate, TypingProfile
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

    def __init__(
        self,
        service: TypingService,
        plan: SplitPlan,
        profile: TypingProfile,
        target: int,
    ) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.profile = profile
        self.target = target

    @Slot()
    def run(self) -> None:
        try:
            self.service.run(
                self.plan,
                self.profile,
                self.target,
                self.progress.emit,
            )
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
        self.store = store
        self.state = store.load()
        self.splitter = SmartSplitter()
        self.service = None
        self.worker_thread = None
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
        self.setMinimumSize(1040, 680)
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
        shell.setContentsMargins(20, 16, 20, 14)
        shell.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        mark = QLabel("TX")
        mark.setObjectName("mark")
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        identity = QVBoxLayout()
        identity.setSpacing(0)
        brand = QLabel("TyperX")
        brand.setObjectName("brand")
        tagline = QLabel("NATURAL INPUT STUDIO")
        tagline.setObjectName("eyebrow")
        identity.addWidget(brand)
        identity.addWidget(tagline)

        self.status = QLabel("Готов · F8 старт · F9 стоп")
        self.status.setObjectName("status")
        self.status.setMinimumWidth(220)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stop = QPushButton("Стоп · F9")
        self.stop.setObjectName("quiet")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_typing)

        self.start = QPushButton("Запустить через 3 сек")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.start_countdown)

        header.addWidget(mark)
        header.addLayout(identity)
        header.addStretch()
        header.addWidget(self.status)
        header.addWidget(self.stop)
        header.addWidget(self.start)
        shell.addLayout(header)

        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFrameShape(QFrame.Shape.HLine)
        shell.addWidget(rule)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("workspaceSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._templates_panel())
        splitter.addWidget(self._editor_panel())
        splitter.addWidget(self._settings_panel())
        splitter.setSizes([230, 720, 292])
        shell.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.setSpacing(16)
        privacy = QLabel("Локально. Без аккаунта. Без облака.")
        privacy.setObjectName("muted")
        hotkeys = QLabel("F8 запуск   F9 стоп   F10 пауза")
        hotkeys.setObjectName("mono")
        footer.addWidget(privacy)
        footer.addStretch()
        footer.addWidget(hotkeys)
        shell.addLayout(footer)
        self.setCentralWidget(root)

    @staticmethod
    def _panel(role: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName(role)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        return frame, layout

    @staticmethod
    def _eyebrow(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("eyebrow")
        return label

    def _templates_panel(self) -> QFrame:
        panel, layout = self._panel("library")
        heading = QLabel("Библиотека")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        layout.addWidget(self._eyebrow("ТЕКСТЫ И ШАБЛОНЫ"))

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Найти текст...")
        self.search.textChanged.connect(self._filter_templates)
        layout.addWidget(self.search)

        self.templates = QListWidget()
        self.templates.setObjectName("templates")
        self.templates.setSpacing(2)
        self.templates.currentItemChanged.connect(self._template_selected)
        layout.addWidget(self.templates, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        add = QPushButton("+ Новый")
        add.clicked.connect(self._new_template)
        self.delete = QPushButton("Удалить")
        self.delete.setObjectName("danger")
        self.delete.clicked.connect(self._delete_template)
        actions.addWidget(add, 1)
        actions.addWidget(self.delete)
        layout.addLayout(actions)
        panel.setMinimumWidth(210)
        panel.setMaximumWidth(320)
        return panel

    def _editor_panel(self) -> QFrame:
        panel, layout = self._panel("editorPanel")

        top = QHBoxLayout()
        top.setSpacing(12)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title_stack.addWidget(self._eyebrow("АКТИВНЫЙ ТЕКСТ"))
        self.title = QLineEdit()
        self.title.setObjectName("titleInput")
        self.title.setPlaceholderText("Название шаблона")
        title_stack.addWidget(self.title)
        self.counter = QLabel("0 знаков")
        self.counter.setObjectName("mono")
        self.save = QPushButton("Сохранить")
        self.save.setObjectName("quiet")
        self.save.clicked.connect(self._save_current)
        top.addLayout(title_stack, 1)
        top.addWidget(self.counter, 0, Qt.AlignmentFlag.AlignBottom)
        top.addWidget(self.save, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(top)

        self.editor = QTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText(
            "Вставь текст. TyperX разобьёт его на живые сообщения и сохранит ритм."
        )
        self.editor.textChanged.connect(self._content_changed)
        self.title.textChanged.connect(self._content_changed)
        layout.addWidget(self.editor, 3)

        preview_header = QHBoxLayout()
        preview_title = QLabel("Очередь отправки")
        preview_title.setObjectName("sectionTitle")
        self.plan_meta = QLabel("0 сообщений")
        self.plan_meta.setObjectName("mono")
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.plan_meta)
        layout.addLayout(preview_header)

        self.preview = QListWidget()
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(160)
        self.preview.setSpacing(4)
        layout.addWidget(self.preview, 2)
        return panel

    def _settings_panel(self) -> QFrame:
        panel, layout = self._panel("inspector")
        heading = QLabel("Ритм")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        self.wpm, self.wpm_value = self._slider(layout, "Скорость", 25, 300)
        self.variation, self.variation_value = self._slider(layout, "Разброс", 0, 55)
        self.typos, self.typos_value = self._slider(layout, "Опечатки", 0, 40)

        layout.addSpacing(8)
        layout.addWidget(self._eyebrow("ПОВЕДЕНИЕ"))
        self.smart = QCheckBox("Делить по смыслу")
        self.fix_typos = QCheckBox("Добавлять живые опечатки")
        self.pause_marks = QCheckBox("Паузы после знаков")
        self.keep_marks = QCheckBox("Сохранять пунктуацию")
        for checkbox in (
            self.smart,
            self.fix_typos,
            self.pause_marks,
            self.keep_marks,
        ):
            checkbox.toggled.connect(self._settings_changed)
            layout.addWidget(checkbox)

        note = QLabel(
            "TyperX останавливается при смене окна. В Monkeytype ошибки видны, "
            "а затем исправляются через Backspace."
        )
        note.setObjectName("note")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        panel.setMinimumWidth(270)
        panel.setMaximumWidth(350)
        return panel

    def _slider(
        self,
        layout: QVBoxLayout,
        name: str,
        minimum: int,
        maximum: int,
    ) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        label = QLabel(name)
        label.setObjectName("controlLabel")
        value = QLabel()
        value.setObjectName("value")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.valueChanged.connect(self._settings_changed)
        layout.addLayout(row)
        layout.addWidget(slider)
        return slider, value

    def _populate_templates(self) -> None:
        self.templates.clear()
        for template in self.state.templates:
            item = QListWidgetItem(template.title)
            item.setData(Qt.ItemDataRole.UserRole, template.id)
            item.setToolTip(template.text[:240])
            self.templates.addItem(item)

    def _select_initial(self) -> None:
        for index in range(self.templates.count()):
            item = self.templates.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == self.state.selected_template_id:
                self.templates.setCurrentRow(index)
                return
        if self.templates.count():
            self.templates.setCurrentRow(0)

    def _load_profile(self, profile: TypingProfile) -> None:
        self.wpm.setValue(profile.wpm)
        self.variation.setValue(profile.variation)
        self.typos.setValue(round(profile.typo_rate))
        self.smart.setChecked(profile.smart_split)
        self.fix_typos.setChecked(profile.fix_typos)
        self.pause_marks.setChecked(profile.punctuation_pauses)
        self.keep_marks.setChecked(profile.keep_punctuation)
        self._refresh_labels()

    def _profile(self) -> TypingProfile:
        return TypingProfile(
            wpm=self.wpm.value(),
            variation=self.variation.value(),
            typo_rate=float(self.typos.value()),
            smart_split=self.smart.isChecked(),
            fix_typos=self.fix_typos.isChecked(),
            punctuation_pauses=self.pause_marks.isChecked(),
            keep_punctuation=self.keep_marks.isChecked(),
        ).normalized()

    def _current_template(self) -> TextTemplate | None:
        item = self.templates.currentItem()
        if not item:
            return None
        template_id = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (template for template in self.state.templates if template.id == template_id),
            None,
        )

    def _template_selected(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
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
        self._refresh_preview()

    def _settings_changed(self) -> None:
        if self._loading:
            return
        self._refresh_labels()
        self._refresh_preview()
        self._schedule_save()

    def _refresh_labels(self) -> None:
        self.wpm_value.setText(f"{self.wpm.value()} WPM")
        self.variation_value.setText(f"{self.variation.value()}%")
        self.typos_value.setText(f"{self.typos.value()}% слов")

    def _refresh_preview(self) -> None:
        text = self.editor.toPlainText()
        self.counter.setText(f"{len(text):,} знаков".replace(",", " "))
        self.preview.clear()
        plan = self.splitter.plan(text, self._profile(), seed=hash(text) & 0xFFFFFFFF)
        for index, message in enumerate(plan.messages, start=1):
            item = QListWidgetItem(f"{index:02d}   {message}")
            item.setToolTip(message)
            self.preview.addItem(item)
        self.plan_meta.setText(
            f"{len(plan.messages)} сообщений · {plan.character_count} знаков"
        )
        self.start.setEnabled(bool(plan.messages) and self.worker_thread is None)

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
            clone = new_template(
                self.title.text().strip() or template.title,
                self.editor.toPlainText(),
            )
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
        answer = QMessageBox.question(
            self,
            "Удалить шаблон?",
            f"«{template.title}» нельзя будет восстановить.",
        )
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
            template = next(
                entry for entry in self.state.templates if entry.id == template_id
            )
            haystack = f"{template.title} {template.text}".casefold()
            item.setHidden(needle not in haystack)

    def start_countdown(self) -> None:
        if self.worker_thread is not None:
            return
        self.showMinimized()
        self._countdown(3)

    def _countdown(self, remaining: int) -> None:
        if remaining <= 0:
            self._hotkey_start()
            return
        self.status.setText(f"Выбери окно: старт через {remaining}")
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
        self.start.setEnabled(bool(self.editor.toPlainText().strip()))
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
