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
    QScrollArea,
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
        self.setMinimumSize(1120, 720)
        self.setStyleSheet(stylesheet())
        self._build_ui()
        self._populate_templates()
        self._load_profile(self.state.profile)
        self._loading = False
        self._select_initial()
        self.hotkeys.start()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        shell = QVBoxLayout(root)
        shell.setContentsMargins(20, 18, 20, 16)
        shell.setSpacing(14)
        shell.addWidget(self._top_bar())

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(10)
        body.addWidget(self._library_panel())
        body.addWidget(self._workspace_panel())
        body.addWidget(self._settings_panel())
        body.setSizes([245, 650, 290])
        shell.addWidget(body, 1)
        shell.addWidget(self._run_bar())
        self.setCentralWidget(root)

    def _top_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("topBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        mark = QLabel("TX")
        mark.setFixedSize(38, 38)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("background:#7650c9;color:#fdfbff;border-radius:11px;font-weight:800")
        brand = QLabel("TyperX")
        brand.setObjectName("brand")
        context = QLabel("typing studio")
        context.setObjectName("muted")
        self.status = QLabel("Готов · F8 старт · F9 стоп")
        self.status.setObjectName("status")
        layout.addWidget(mark)
        layout.addWidget(brand)
        layout.addWidget(context)
        layout.addStretch()
        layout.addWidget(self.status)
        return frame

    def _library_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("library")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(310)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(10)
        heading = QLabel("Библиотека")
        heading.setObjectName("sectionTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти шаблон")
        self.search.textChanged.connect(self._filter_templates)
        self.templates = QListWidget()
        self.templates.currentItemChanged.connect(self._template_selected)
        actions = QHBoxLayout()
        add = QPushButton("+ Новый")
        add.clicked.connect(self._new_template)
        self.delete = QPushButton("Удалить")
        self.delete.setObjectName("danger")
        self.delete.clicked.connect(self._delete_template)
        actions.addWidget(add)
        actions.addWidget(self.delete)
        layout.addWidget(heading)
        layout.addWidget(self.search)
        layout.addWidget(self.templates, 1)
        layout.addLayout(actions)
        return panel

    def _workspace_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("workspace")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        intro = QHBoxLayout()
        page = QLabel("Текст и отправка")
        page.setObjectName("pageTitle")
        self.counter = QLabel("0 знаков")
        self.counter.setObjectName("muted")
        intro.addWidget(page)
        intro.addStretch()
        intro.addWidget(self.counter)
        self.title = QLineEdit()
        self.title.setObjectName("titleInput")
        self.title.setPlaceholderText("Название шаблона")
        self.title.textChanged.connect(self._content_changed)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Вставь текст. TyperX превратит его в естественную переписку.")
        self.editor.textChanged.connect(self._content_changed)
        preview_header = QHBoxLayout()
        preview_title = QLabel("План сообщений")
        preview_title.setObjectName("sectionTitle")
        self.plan_meta = QLabel()
        self.plan_meta.setObjectName("muted")
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.plan_meta)
        self.preview = QListWidget()
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(150)
        self.save = QPushButton("Сохранить шаблон")
        self.save.clicked.connect(self._save_current)
        layout.addLayout(intro)
        layout.addWidget(self.title)
        layout.addWidget(self.editor, 3)
        layout.addLayout(preview_header)
        layout.addWidget(self.preview, 2)
        layout.addWidget(self.save, 0, Qt.AlignmentFlag.AlignRight)
        return panel

    def _settings_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(270)
        scroll.setMaximumWidth(340)
        panel = QFrame()
        panel.setObjectName("inspector")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 4, 4, 4)
        layout.setSpacing(10)
        title = QLabel("Настройка ритма")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.wpm, self.wpm_value = self._slider(layout, "Скорость", 25, 300)
        self.variation, self.variation_value = self._slider(layout, "Разброс", 0, 55)
        self.typos, self.typos_value = self._slider(layout, "Опечатки", 0, 40)
        layout.addSpacing(6)
        layout.addWidget(self._eyebrow("ПОВЕДЕНИЕ"))
        self.smart = QCheckBox("Умно делить на сообщения")
        self.fix_typos = QCheckBox("Добавлять живые опечатки")
        self.pause_marks = QCheckBox("Паузы после пунктуации")
        self.keep_marks = QCheckBox("Сохранять пунктуацию")
        for checkbox in (self.smart, self.fix_typos, self.pause_marks, self.keep_marks):
            checkbox.toggled.connect(self._settings_changed)
            layout.addWidget(checkbox)
        self._build_extra_settings(layout)
        note = QLabel("F8 запускает ввод в активном окне. Смена окна мгновенно останавливает печать.")
        note.setWordWrap(True)
        note.setObjectName("note")
        layout.addWidget(note)
        layout.addStretch()
        scroll.setWidget(panel)
        return scroll

    def _build_extra_settings(self, layout: QVBoxLayout) -> None:
        del layout

    def _run_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("runBar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 12, 10)
        label = QLabel("Фокусни поле ввода, затем запускай")
        label.setObjectName("helper")
        hotkeys = QLabel("F8 start   F9 stop   F10 pause")
        hotkeys.setObjectName("muted")
        self.stop = QPushButton("Остановить")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_typing)
        self.start = QPushButton("Начать через 3 секунды")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.start_countdown)
        layout.addWidget(label)
        layout.addWidget(hotkeys)
        layout.addStretch()
        layout.addWidget(self.stop)
        layout.addWidget(self.start)
        return frame

    @staticmethod
    def _eyebrow(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("eyebrow")
        return label

    def _slider(self, layout: QVBoxLayout, name: str, minimum: int, maximum: int):
        row = QHBoxLayout()
        row.addWidget(QLabel(name))
        row.addStretch()
        value = QLabel()
        value.setObjectName("value")
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

    def _current_template(self):
        item = self.templates.currentItem()
        if not item:
            return None
        template_id = item.data(Qt.ItemDataRole.UserRole)
        return next((x for x in self.state.templates if x.id == template_id), None)

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
        self._refresh_preview()
        self._schedule_save()

    def _refresh_labels(self) -> None:
        self.wpm_value.setText(f"{self.wpm.value()} WPM")
        self.variation_value.setText(f"{self.variation.value()}%")
        self.typos_value.setText(f"{self.typos.value()}% слов")

    def _refresh_preview(self) -> None:
        text = self.editor.toPlainText()
        self.preview.clear()
        plan = self.splitter.plan(text, self._profile(), seed=hash(text) & 0xFFFFFFFF)
        for number, message in enumerate(plan.messages, 1):
            item = QListWidgetItem(f"{number:02}   {message}")
            item.setToolTip(message)
            self.preview.addItem(item)
        self.plan_meta.setText(f"{len(plan.messages)} сообщений · {plan.character_count} знаков")
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
        if QMessageBox.question(self, "Удалить шаблон?", f"«{template.title}» нельзя будет восстановить.") != QMessageBox.StandardButton.Yes:
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
            template = next(x for x in self.state.templates if x.id == template_id)
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
        self.status.setText(f"Фокус на поле ввода: старт через {remaining}")
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
