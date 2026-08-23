PALETTE = {
    "canvas": "#f1f0eb",
    "surface": "#fbfaf6",
    "surface_alt": "#e9ecf5",
    "ink": "#182033",
    "muted": "#697083",
    "line": "#d5d7de",
    "accent": "#3157d5",
    "accent_hover": "#2849b7",
    "accent_soft": "#dfe6ff",
    "danger": "#b33b52",
    "success": "#24715a",
}


def stylesheet() -> str:
    p = PALETTE
    return f"""
    * {{
        color: {p['ink']};
        font-family: "Segoe UI Variable", "Segoe UI";
        selection-background-color: {p['accent']};
        selection-color: {p['surface']};
    }}
    QWidget#root, QMainWindow {{ background: {p['canvas']}; }}
    QLabel#mark {{
        background: {p['ink']};
        color: {p['surface']};
        border-radius: 8px;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#brand {{ font-size: 24px; font-weight: 800; }}
    QLabel#sectionTitle {{ font-size: 20px; font-weight: 750; }}
    QLabel#eyebrow {{
        color: {p['muted']};
        font-size: 9px;
        font-weight: 750;
        letter-spacing: 1.3px;
    }}
    QLabel#muted {{ color: {p['muted']}; }}
    QLabel#mono {{
        color: {p['muted']};
        font-family: "Cascadia Mono", "Consolas";
        font-size: 10px;
    }}
    QLabel#status {{
        color: {p['accent']};
        background: {p['accent_soft']};
        border-radius: 7px;
        padding: 8px 12px;
        font-weight: 700;
    }}
    QLabel#controlLabel {{ font-size: 12px; font-weight: 650; }}
    QLabel#value {{
        color: {p['accent']};
        font-family: "Cascadia Mono", "Consolas";
        font-size: 10px;
        font-weight: 700;
    }}
    QLabel#note {{
        color: {p['muted']};
        background: {p['surface_alt']};
        border: 1px solid {p['line']};
        border-radius: 8px;
        padding: 12px;
        line-height: 1.35;
    }}
    QFrame#rule {{ color: {p['line']}; background: {p['line']}; max-height: 1px; }}
    QFrame#library {{
        background: {p['ink']};
        border: none;
        border-radius: 10px;
    }}
    QFrame#library QLabel#sectionTitle,
    QFrame#library QLabel#eyebrow {{ color: {p['surface']}; }}
    QFrame#editorPanel {{
        background: {p['surface']};
        border: 1px solid {p['line']};
        border-radius: 10px;
    }}
    QFrame#inspector {{
        background: {p['surface_alt']};
        border: 1px solid {p['line']};
        border-radius: 10px;
    }}
    QSplitter::handle {{ background: transparent; }}
    QLineEdit, QTextEdit {{
        background: {p['surface']};
        border: 1px solid {p['line']};
        border-radius: 7px;
        padding: 9px 11px;
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border: 2px solid {p['accent']};
        padding: 8px 10px;
    }}
    QLineEdit#titleInput {{
        background: transparent;
        border: none;
        border-radius: 0;
        padding: 0;
        font-size: 22px;
        font-weight: 750;
    }}
    QLineEdit#titleInput:focus {{ border-bottom: 2px solid {p['accent']}; }}
    QLineEdit#search {{
        background: #252e43;
        color: {p['surface']};
        border: 1px solid #3a4358;
    }}
    QLineEdit#search:focus {{ border: 2px solid #7892eb; }}
    QTextEdit#editor {{
        font-family: "Cascadia Mono", "Consolas";
        font-size: 14px;
        line-height: 1.5;
        padding: 16px;
    }}
    QListWidget {{ border: none; outline: none; }}
    QListWidget#templates {{ background: transparent; color: #dce1ec; }}
    QListWidget#templates::item {{
        color: #dce1ec;
        border-radius: 6px;
        padding: 10px 9px;
        margin: 1px 0;
    }}
    QListWidget#templates::item:hover {{ background: #252e43; }}
    QListWidget#templates::item:selected {{
        background: {p['accent']};
        color: {p['surface']};
    }}
    QListWidget#preview {{ background: transparent; }}
    QListWidget#preview::item {{
        background: {p['canvas']};
        border: 1px solid {p['line']};
        border-radius: 7px;
        padding: 9px 11px;
        color: #3d4558;
    }}
    QListWidget#preview::item:selected {{
        background: {p['accent_soft']};
        color: {p['accent']};
    }}
    QPushButton {{
        min-height: 38px;
        border: 1px solid {p['line']};
        border-radius: 7px;
        padding: 0 14px;
        background: {p['surface']};
        font-weight: 700;
    }}
    QPushButton:hover {{ background: #e9e8e3; }}
    QPushButton:pressed {{ background: #deddd8; }}
    QPushButton:disabled {{ color: #9ca1ae; background: #e8e8e5; }}
    QPushButton#primary {{
        min-height: 42px;
        background: {p['accent']};
        color: {p['surface']};
        border-color: {p['accent']};
        padding: 0 18px;
    }}
    QPushButton#primary:hover {{ background: {p['accent_hover']}; }}
    QPushButton#quiet {{ background: transparent; }}
    QPushButton#danger {{ color: {p['danger']}; background: transparent; }}
    QFrame#library QPushButton {{
        background: #252e43;
        color: #e9edf5;
        border-color: #3a4358;
    }}
    QFrame#library QPushButton:hover {{ background: #303a52; }}
    QFrame#library QPushButton#danger {{ color: #ff9daf; }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: #cdd1dc;
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 16px;
        margin: -6px 0;
        border-radius: 8px;
        background: {p['surface']};
        border: 2px solid {p['accent']};
    }}
    QCheckBox {{ spacing: 9px; padding: 4px 0; }}
    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        background: {p['surface']};
        border: 1px solid #aeb4c2;
        border-radius: 4px;
    }}
    QCheckBox::indicator:checked {{
        background: {p['accent']};
        border-color: {p['accent']};
    }}
    QScrollBar:vertical {{ width: 8px; background: transparent; }}
    QScrollBar::handle:vertical {{
        background: #bfc3cd;
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{
        color: {p['surface']};
        background: {p['ink']};
        border: 1px solid #3a4358;
        padding: 7px;
    }}
    """
