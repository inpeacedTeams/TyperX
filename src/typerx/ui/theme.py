PALETTE = {
    "canvas": "#f4f3f8",
    "surface": "#faf9fd",
    "surface_alt": "#efedf5",
    "surface_strong": "#e7e3ef",
    "ink": "#272331",
    "muted": "#716b7c",
    "line": "#ddd8e6",
    "accent": "#7650c9",
    "accent_hover": "#6842b8",
    "accent_soft": "#ede7fa",
    "danger": "#b5415a",
    "success": "#26745a",
}


def stylesheet() -> str:
    p = PALETTE
    return f"""
    * {{
        color: {p['ink']};
        selection-background-color: {p['accent']};
        selection-color: #fdfbff;
    }}
    QMainWindow, QWidget#appRoot {{ background: {p['canvas']}; }}
    QFrame#topBar, QFrame#runBar {{
        background: {p['surface']};
        border: 1px solid {p['line']};
        border-radius: 16px;
    }}
    QFrame#library {{
        background: {p['surface_alt']};
        border: 1px solid {p['line']};
        border-radius: 16px;
    }}
    QFrame#workspace {{
        background: {p['surface']};
        border: 1px solid {p['line']};
        border-radius: 16px;
    }}
    QFrame#inspector {{
        background: transparent;
        border: none;
    }}
    QLabel#brand {{ font-size: 22px; font-weight: 750; }}
    QLabel#pageTitle {{ font-size: 28px; font-weight: 760; }}
    QLabel#sectionTitle {{ font-size: 16px; font-weight: 700; }}
    QLabel#eyebrow {{ color: {p['muted']}; font-size: 10px; font-weight: 750; }}
    QLabel#muted, QLabel#helper {{ color: {p['muted']}; }}
    QLabel#status {{
        color: {p['accent']};
        background: {p['accent_soft']};
        border-radius: 11px;
        padding: 7px 11px;
        font-weight: 650;
    }}
    QLabel#value {{ color: {p['accent']}; font-weight: 750; }}
    QLabel#note {{
        color: {p['muted']};
        background: {p['surface_alt']};
        border: 1px solid {p['line']};
        border-radius: 11px;
        padding: 11px;
    }}
    QLineEdit, QTextEdit {{
        background: {p['surface_alt']};
        border: 1px solid {p['line']};
        border-radius: 11px;
        padding: 9px 11px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border: 2px solid {p['accent']}; padding: 8px 10px; }}
    QLineEdit#titleInput {{
        background: transparent;
        border: none;
        border-radius: 0;
        padding: 2px 0;
        font-size: 20px;
        font-weight: 700;
    }}
    QLineEdit#titleInput:focus {{ border: none; padding: 2px 0; }}
    QTextEdit {{ font-size: 15px; }}
    QListWidget {{ background: transparent; border: none; padding: 0; outline: none; }}
    QListWidget::item {{ border-radius: 9px; padding: 10px; margin: 2px 0; }}
    QListWidget::item:hover {{ background: {p['surface_strong']}; }}
    QListWidget::item:selected {{ background: {p['accent_soft']}; color: {p['accent']}; }}
    QListWidget#preview {{
        background: {p['surface_alt']};
        border: 1px solid {p['line']};
        border-radius: 11px;
        padding: 7px;
    }}
    QListWidget#preview::item {{ background: {p['surface']}; border: 1px solid {p['line']}; }}
    QPushButton {{
        min-height: 40px;
        border: 1px solid {p['line']};
        border-radius: 10px;
        padding: 0 14px;
        background: {p['surface']};
        font-weight: 650;
    }}
    QPushButton:hover {{ background: {p['surface_alt']}; }}
    QPushButton:pressed {{ background: {p['surface_strong']}; }}
    QPushButton:focus {{ border: 2px solid {p['accent']}; }}
    QPushButton:disabled {{ color: #aaa4b2; background: {p['surface_alt']}; }}
    QPushButton#primary {{ background: {p['accent']}; color: #fdfbff; border-color: {p['accent']}; min-height: 46px; }}
    QPushButton#primary:hover {{ background: {p['accent_hover']}; }}
    QPushButton#danger {{ color: {p['danger']}; }}
    QPushButton#quiet {{ background: transparent; border-color: transparent; }}
    QSlider::groove:horizontal {{ height: 5px; background: {p['line']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 17px;
        margin: -7px 0;
        border-radius: 8px;
        background: {p['surface']};
        border: 2px solid {p['accent']};
    }}
    QCheckBox {{ spacing: 9px; padding: 4px 0; }}
    QCheckBox::indicator {{
        width: 19px;
        height: 19px;
        border: 1px solid #b8b1c3;
        border-radius: 6px;
        background: {p['surface']};
    }}
    QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
    QSplitter::handle {{ background: transparent; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ width: 8px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: #c7c0cf; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
