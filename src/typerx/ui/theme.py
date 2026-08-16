PALETTE = {
    "canvas": "#f5f3ef", "surface": "#fbfaf7", "surface2": "#efedf1", "ink": "#252229",
    "muted": "#77717e", "line": "#ded9e2", "accent": "#6d43c5", "accent2": "#eee8fa",
    "danger": "#b63f55", "success": "#2e7b5b",
}


def stylesheet() -> str:
    p = PALETTE
    return f"""
    * {{ color: {p['ink']}; selection-background-color: {p['accent']}; selection-color: #fbf9ff; }}
    QMainWindow {{ background: {p['canvas']}; }}
    QFrame#panel {{ background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 18px; }}
    QLabel#brand {{ font-size: 24px; font-weight: 750; }}
    QLabel#eyebrow {{ color: {p['muted']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#status {{ color: {p['accent']}; background: {p['accent2']}; border-radius: 14px; padding: 7px 12px; font-weight: 650; }}
    QListWidget, QTextEdit, QLineEdit {{ background: {p['surface2']}; border: 1px solid {p['line']}; border-radius: 12px; padding: 9px; }}
    QListWidget {{ background: transparent; border: none; padding: 0; outline: none; }}
    QListWidget::item {{ border-radius: 10px; padding: 10px; margin: 2px 0; }}
    QListWidget::item:hover {{ background: {p['surface2']}; }}
    QListWidget::item:selected {{ background: {p['accent2']}; color: {p['accent']}; }}
    QTextEdit {{ font-size: 15px; line-height: 1.45; }}
    QPushButton {{ min-height: 40px; border: none; border-radius: 11px; padding: 0 15px; background: {p['surface2']}; font-weight: 650; }}
    QPushButton:hover {{ background: #e7e3ea; }}
    QPushButton:pressed {{ background: #ddd7e2; }}
    QPushButton:disabled {{ color: #a7a1aa; background: #eeebef; }}
    QPushButton#primary {{ background: {p['accent']}; color: #fbf9ff; }}
    QPushButton#primary:hover {{ background: #5f38b2; }}
    QPushButton#danger {{ color: {p['danger']}; }}
    QSlider::groove:horizontal {{ height: 5px; background: #ded9e2; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 17px; margin: -6px 0; border-radius: 8px; background: {p['surface']}; border: 2px solid {p['accent']}; }}
    QCheckBox {{ spacing: 9px; padding: 4px 0; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid #bbb4c2; border-radius: 5px; background: {p['surface']}; }}
    QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
    QScrollBar:vertical {{ width: 8px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: #cbc5ce; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
