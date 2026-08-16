from __future__ import annotations

import logging
import threading
import uuid

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSlider, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)

from typerx.domain.models import AppState, TextTemplate, TypingProfile
from typerx.domain.splitter import SmartSplitter, SplitPlan
from typerx.persistence.store import AppStore, new_template
from typerx.platform.windows import FocusChangedError, GlobalHotkeys, UnsupportedPlatformError, WindowsInput
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
        except Exception:
            LOGGER.exception("Typing worker failed")
            self.failed.emit("Ввод остановлен из-за системной ошибки")


class MainWindow(QMainWindow):
    def __init__(self, store: AppStore) -> None:
        super().__init__()
        self.store = store
        self.state = store.load()
        self.splitter = SmartSplitter()
        self.service: TypingService | None = None
        self.worker_thread: QThread | None = None
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
        shell = QVBoxLayout(root)
        shell.setContentsMargins(24, 20, 24, 18)
        shell.setSpacing(18)

        header = QHBoxLayout()
        logo = QLabel("Tx")
        logo.setFixedSize(42, 42)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background:#6d43c5;color:#fbf9ff;border-radius:13px;font-size:17px;font-weight:800")
        brand_box = QVBoxLayout(); brand_box.setSpacing(0)
        brand = QLabel("TyperX"); brand.setObjectName("brand")
        tagline = QLabel("human rhythm, smart messages"); tagline.setObjectName("muted")
        brand_box.addWidget(brand); brand_box.addWidget(tagline)
        self.status = QLabel("Готов · F8 старт · F9 стоп"); self.status.setObjectName("status")
        header.addWidget(logo); header.addLayout(brand_box); header.addStretch(); header.addWidget(self.status)
        shell.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._templates_panel())
        splitter.addWidget(self._editor_panel())
        splitter.addWidget(self._settings_panel())
        splitter.setSizes([245, 680, 285])
        splitter.setHandleWidth(14)
        shell.addWidget(splitter, 1)

        footer = QHBoxLayout()
        left = QLabel("Локально · без аккаунта · без облака"); left.setObjectName("muted")
        right = QLabel("Windows 10/11 · v1.0"); right.setObjectName("muted")
        footer.addWidget(left); footer.addStretch(); footer.addWidget(right)
        shell.addLayout(footer)
        self.setCentralWidget(root)

    def _panel(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(); frame.setObjectName("panel")
        layout = QVBoxLayout(frame); layout.setContentsMargins(16, 16, 16, 16); layout.setSpacing(11)
        return frame, layout

    @staticmethod
    def _eyebrow(text: str) -> QLabel:
        label = QLabel(text); label.setObjectName("eyebrow"); return label

    def _templates_panel(self) -> QFrame:
        panel, layout = self._panel()
        layout.addWidget(self._eyebrow("ШАБЛОНЫ"))
        self.search = QLineEdit(); self.search.setPlaceholderText("Поиск")
        self.search.textChanged.connect(self._filter_templates)
        layout.addWidget(self.search)
        self.templates = QListWidget(); self.templates.currentItemChanged.connect(self._template_selected)
        layout.addWidget(self.templates, 1)
        actions = QHBoxLayout()
        add = QPushButton("Новый"); add.clicked.connect(self._new_template)
        self.delete = QPushButton("Удалить"); self.delete.setObjectName("danger"); self.delete.clicked.connect(self._delete_template)
        actions.addWidget(add); actions.addWidget(self.delete)
        layout.addLayout(actions)
        panel.setMinimumWidth(220); panel.setMaximumWidth(330)
        return panel

    def _editor_panel(self) -> QFrame:
        panel, layout = self._panel()
        title_row = QHBoxLayout()
        self.title = QLineEdit(); self.title.setPlaceholderText("Название шаблона")
        self.counter = QLabel("0 знаков"); self.counter.setObjectName("muted")
        title_row.addWidget(self.title, 1); title_row.addWidget(self.counter)
        layout.addLayout(title_row)
        self.editor = QTextEdit(); self.editor.setPlaceholderText("Вставь текст. TyperX соберёт естественный план отправки…")
        self.editor.textChanged.connect(self._content_changed)
        self.title.textChanged.connect(self._content_changed)
        layout.addWidget(self.editor, 3)
        preview_header = QHBoxLayout()
        preview_header.addWidget(self._eyebrow("ПРЕДПРОСМОТР СООБЩЕНИЙ")); preview_header.addStretch()
        self.plan_meta = QLabel(); self.plan_meta.setObjectName("muted"); preview_header.addWidget(self.plan_meta)
        layout.addLayout(preview_header)
        self.preview = QListWidget(); self.preview.setMinimumHeight(160)
        layout.addWidget(self.preview, 2)
        self.save = QPushButton("Сохранить изменения"); self.save.clicked.connect(self._save_current)
        layout.addWidget(self.save)
        return panel

    def _settings_panel(self) -> QFrame:
        panel, layout = self._panel()
        layout.addWidget(self._eyebrow("РИТМ"))
        self.wpm, self.wpm_value = self._slider(layout, "Скорость", 25, 280)
        self.variation, self.variation_value = self._slider(layout, "Разброс", 0, 55)
        self.typos, self.typos_value = self._slider(layout, "Опечатки ×10", 0, 70)
        layout.addSpacing(8); layout.addWidget(self._eyebrow("ПОВЕДЕНИЕ"))
        self.smart = QCheckBox("Умно делить на сообщения")
        self.fix_typos = QCheckBox("Исправлять редкие опечатки")
        self.pause_marks = QCheckBox("Задумываться после знаков")
        self.keep_marks = QCheckBox("Сохранять пунктуацию")
        for checkbox in (self.smart, self.fix_typos, self.pause_marks, self.keep_marks):
            checkbox.toggled.connect(self._settings_changed); layout.addWidget(checkbox)
        note = QLabel("Фокус защищён: если переключить окно во время работы, TyperX сразу остановит ввод.")
        note.setWordWrap(True); note.setObjectName("muted")
        note.setStyleSheet("background:#f0ecf7;border-radius:12px;padding:12px;line-height:1.4")
        layout.addWidget(note); layout.addStretch()
        self.start = QPushButton("Начать через 3 секунды"); self.start.setObjectName("primary"); self.start.clicked.connect(self.start_countdown)
        self.stop = QPushButton("Остановить · F9"); self.stop.setEnabled(False); self.stop.clicked.connect(self.stop_typing)
        layout.addWidget(self.start); layout.addWidget(self.stop)
        panel.setMinimumWidth(265); panel.setMaximumWidth(340)
        return panel

    def _slider(self, layout: QVBoxLayout, name: str, minimum: int, maximum: int) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout(); row.addWidget(QLabel(name)); row.addStretch()
        value = QLabel(); value.setStyleSheet("color:#6d43c5;font-weight:700"); row.addWidget(value)
        slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(minimum, maximum); slider.valueChanged.connect(self._settings_changed)
        layout.addLayout(row); layout.addWidget(slider)
        return slider, value

    def _populate_templates(self) -> None:
        self.templates.clear()
        for template in self.state.templates:
            item = QListWidgetItem(template.title); item.setData(Qt.ItemDataRole.UserRole, template.id); self.templates.addItem(item)

    def _select_initial(self) -> None:
        for index in range(self.templates.count()):
            if self.templates.item(index).data(Qt.ItemDataRole.UserRole) == self.state.selected_template_id:
                self.templates.setCurrentRow(index); return
        if self.templates.count(): self.templates.setCurrentRow(0)

    def _load_profile(self, p: TypingProfile) -> None:
        self.wpm.setValue(p.wpm); self.variation.setValue(p.variation); self.typos.setValue(round(p.typo_rate * 10))
        self.smart.setChecked(p.smart_split); self.fix_typos.setChecked(p.fix_typos)
        self.pause_marks.setChecked(p.punctuation_pauses); self.keep_marks.setChecked(p.keep_punctuation)
        self._refresh_labels()

    def _profile(self) -> TypingProfile:
        return TypingProfile(wpm=self.wpm.value(), variation=self.variation.value(), typo_rate=self.typos.value() / 10,
            smart_split=self.smart.isChecked(), fix_typos=self.fix_typos.isChecked(),
            punctuation_pauses=self.pause_marks.isChecked(), keep_punctuation=self.keep_marks.isChecked()).normalized()

    def _current_template(self) -> TextTemplate | None:
        item = self.templates.currentItem()
        if not item: return None
        template_id = item.data(Qt.ItemDataRole.UserRole)
        return next((x for x in self.state.templates if x.id == template_id), None)

    def _template_selected(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        if current is None: return
        template = self._current_template()
        if template is None: return
        self._loading = True; self.title.setText(template.title); self.editor.setPlainText(template.text); self._loading = False
        self.state.selected_template_id = template.id; self.delete.setEnabled(not template.builtin); self._refresh_preview(); self._schedule_save()

    def _content_changed(self) -> None:
        if self._loading: return
        self.counter.setText(f"{len(self.editor.toPlainText())} знаков")
        self._refresh_preview()

    def _settings_changed(self) -> None:
        if self._loading: return
        self._refresh_labels(); self._refresh_preview(); self._schedule_save()

    def _refresh_labels(self) -> None:
        self.wpm_value.setText(f"{self.wpm.value()} WPM"); self.variation_value.setText(f"{self.variation.value()}%")
        self.typos_value.setText(f"{self.typos.value() / 10:.1f}%")

    def _refresh_preview(self) -> None:
        text = self.editor.toPlainText(); self.preview.clear()
        plan = self.splitter.plan(text, self._profile(), seed=hash(text) & 0xFFFFFFFF)
        for message in plan.messages:
            item = QListWidgetItem(message); item.setToolTip(message); self.preview.addItem(item)
        self.plan_meta.setText(f"{len(plan.messages)} сообщений · {plan.character_count} знаков")
        self.start.setEnabled(bool(plan.messages) and self.worker_thread is None)

    def _new_template(self) -> None:
        template = new_template(); self.state.templates.append(template); self._populate_templates()
        self.state.selected_template_id = template.id; self._select_initial(); self.title.selectAll(); self.title.setFocus(); self._schedule_save()

    def _save_current(self) -> None:
        template = self._current_template()
        if template is None: return
        if template.builtin:
            clone = new_template(self.title.text().strip() or template.title, self.editor.toPlainText())
            self.state.templates.append(clone); self.state.selected_template_id = clone.id
        else:
            template.title = self.title.text().strip()[:80] or "Без названия"; template.text = self.editor.toPlainText()[:100_000]
        self._populate_templates(); self._select_initial(); self._persist(); self.status.setText("Сохранено")

    def _delete_template(self) -> None:
        template = self._current_template()
        if template is None or template.builtin: return
        if QMessageBox.question(self, "Удалить шаблон?", f"«{template.title}» нельзя будет восстановить.") != QMessageBox.StandardButton.Yes: return
        self.state.templates.remove(template); self.state.selected_template_id = self.state.templates[0].id; self._populate_templates(); self._select_initial(); self._persist()

    def _filter_templates(self, query: str) -> None:
        needle = query.casefold().strip()
        for i in range(self.templates.count()):
            item = self.templates.item(i); template_id = item.data(Qt.ItemDataRole.UserRole)
            template = next(x for x in self.state.templates if x.id == template_id)
            item.setHidden(needle not in f"{template.title} {template.text}".casefold())

    def start_countdown(self) -> None:
        if self.worker_thread is not None: return
        self.showMinimized(); self._countdown(3)

    def _countdown(self, remaining: int) -> None:
        if remaining <= 0: self._hotkey_start(); return
        self.status.setText(f"Фокус на Telegram: старт через {remaining}")
        QTimer.singleShot(1000, lambda: self._countdown(remaining - 1))

    @Slot()
    def _hotkey_start(self) -> None:
        if self.worker_thread is not None: return
        target = WindowsInput.foreground_window()
        if not target:
            self._error("Не удалось определить активное окно"); return
        plan = self.splitter.plan(self.editor.toPlainText(), self._profile(), seed=None)
        if not plan.messages: return
        self.service = TypingService(); thread = QThread(self); worker = TypingWorker(self.service, plan, self._profile(), target)
        worker.moveToThread(thread); thread.started.connect(worker.run); worker.progress.connect(self._typing_progress)
        worker.finished.connect(self._typing_finished); worker.failed.connect(self._typing_failed)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit); thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_cleared); self.worker_thread = thread
        self.start.setEnabled(False); self.stop.setEnabled(True); thread.start()

    @Slot(int, int)
    def _typing_progress(self, current: int, total: int) -> None: self.status.setText(f"Печатаю {current} из {total}")

    @Slot(str)
    def _typing_finished(self, message: str) -> None: self.status.setText(message)

    @Slot(str)
    def _typing_failed(self, message: str) -> None: self.status.setText("Остановлено"); self._error(message)

    @Slot()
    def _thread_cleared(self) -> None:
        self.worker_thread = None; self.service = None; self.start.setEnabled(bool(self.editor.toPlainText().strip())); self.stop.setEnabled(False)

    @Slot()
    def stop_typing(self) -> None:
        if self.service: self.service.cancel()

    def _error(self, text: str) -> None:
        self.showNormal(); QMessageBox.warning(self, "TyperX", text)

    def _schedule_save(self) -> None:
        if not self._loading: self._save_timer.start(350)

    def _persist(self) -> None:
        self.state.profile = self._profile(); self.state.window_width = self.width(); self.state.window_height = self.height()
        try: self.store.save(self.state)
        except OSError:
            LOGGER.exception("Could not persist state"); self.status.setText("Настройки не сохранены")

    def closeEvent(self, event: object) -> None:
        self.stop_typing(); self.hotkeys.close(); self._persist(); super().closeEvent(event)  # type: ignore[arg-type]
