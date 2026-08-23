from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel

from typerx.domain.models import TypingProfile
from typerx.ui.monkeytype_page import MonkeytypePage, estimate_seconds, format_duration


class MonkeytypeOptionsPage(MonkeytypePage):
    """Monkeytype UI with independent typo and correction controls."""

    def _controls_panel(self):
        panel = super()._controls_panel()
        layout = panel.layout()
        behavior = QLabel("ПОВЕДЕНИЕ ОШИБОК")
        behavior.setObjectName("eyebrow")
        self.correct_typos = QCheckBox("Исправлять опечатки через Backspace")
        self.correct_typos.setToolTip(
            "Выключи, чтобы TyperX оставлял выбранные опечатки в результате теста"
        )
        self.correct_typos.toggled.connect(self._changed)
        layout.addSpacing(4)
        layout.addWidget(behavior)
        layout.addWidget(self.correct_typos)
        return panel

    def load_profile(self, profile: TypingProfile) -> None:
        super().load_profile(profile)
        self.correct_typos.setChecked(profile.correct_typos)
        self._refresh_forecast()

    def apply_to_profile(self, profile: TypingProfile) -> TypingProfile:
        profile = super().apply_to_profile(profile)
        profile.correct_typos = self.correct_typos.isChecked()
        return profile.normalized()

    def _refresh_forecast(self) -> None:
        super()._refresh_forecast()
        enabled = self.typos_enabled.isChecked() and self.typos.value() > 0
        self.correct_typos.setEnabled(enabled)
        if not enabled:
            return
        rate = self.typos.value()
        if self.correct_typos.isChecked():
            self.preview_text.setText("natural  →  natiral  →  natural")
            self.preview_note.setText(
                "Соседняя клавиша, короткая реакция, Backspace, исправление."
            )
        else:
            self.preview_text.setText("natural  →  natiral")
            self.preview_note.setText("Опечатка остаётся в тесте, Backspace не нажимается.")
            self.time_stat.value_label.setText(
                format_duration(estimate_seconds(250, self.wpm.value(), 0))
            )
