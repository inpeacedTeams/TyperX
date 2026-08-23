PALETTE = {
    "canvas": "#f3f0e9",
    "surface": "#faf8f2",
    "surface_strong": "#e9e5dc",
    "ink": "#242321",
    "muted": "#716e67",
    "line": "#d8d3c9",
    "accent": "#d24b35",
    "accent_hover": "#bb3f2d",
    "accent_soft": "#f4ddd6",
    "danger": "#ad3346",
    "success": "#28725a",
}


def stylesheet() -> str:
    p = PALETTE
    return f"""
    * {{
        color: {p['ink']};
        selection-background-color: {p['accent']};
        selection-color: {p['surface']};
    }}
    QMainWindow, QWidget#root {{ background: {p['canvas']}; }}
    QToolTip {{
        background: {p['ink']}; color: {p['surface']}; border: none;
        border-radius: 7px; padding: 7px 9px;
    }}
    QFrame#topbar, QFrame#commandBar {{
        background: transparent; border: none;
    }}
    QFrame#rail {{
        background: {p['ink']}; border: none; border-radius: 18px;
    }}
    QFrame#workspace {{
        background: {p['surface']}; border: 1px solid {p['line']}; border-radius: 18px;
    }}
    QFrame#controls {{
        background: {p['surface_strong']}; border: 1px solid {p['line']}; border-radius: 18px;
    }}
    QFrame#previewStrip {{
        background: {p['canvas']}; border: 1px solid {p['line']}; border-radius: 13px;
    }}
    QLabel#brand {{ font-size: 23px; font-weight: 800; }}
    QLabel#brandMark {{
        background: {p['accent']}; color: {p['surface']}; border-radius: 10px;
        font-size: 15px; font-weight: 800;
    }}
    QLabel#pageTitle {{ font-size: 25px; font-weight: 760; }}
    QLabel#sectionTitle {{ font-size: 16px; font-weight: 720; }}
    QLabel#eyebrow {{
        color: {p['muted']}; font-size: 10px; font-weight: 750; letter-spacing: 1px;
    }}
    QLabel#muted, QLabel#hint {{ color: {p['muted']}; }}
    QLabel#railEyebrow, QLabel#railHint {{ color: #aaa69f; }}
    QLabel#railEyebrow {{ font-size: 10px; font-weight: 750; letter-spacing: 1px; }}
    QLabel#status {{ color: {p['ink']}; font-weight: 650; }}
    QLabel#statusDot {{
        background: {p['success']}; border-radius: 5px; min-width: 10px; max-width: 10px;
        min-height: 10px; max-height: 10px;
    }}
    QLineEdit, QTextEdit {{
        background: {p['canvas']}; border: 1px solid {p['line']}; border-radius: 11px;
        padding: 10px 12px;
    }}
    QLineEdit:hover, QTextEdit:hover {{ border-color: #bdb7ad; }}
    QLineEdit:focus, QTextEdit:focus {{ border: 2px solid {p['accent']}; padding: 9px 11px; }}
    QLineEdit#templateTitle {{
        background: transparent; border: none; border-radius: 0; padding: 0;
        font-size: 20px; font-weight: 720;
    }}
    QLineEdit#templateTitle:focus {{ border: none; padding: 0; }}
    QTextEdit#editor {{ font-size: 16px; }}
    QLineEdit#railSearch {{
        background: #33312e; color: #f3f0e9; border: 1px solid #484540;
    }}
    QListWidget {{ background: transparent; border: none; padding: 0; outline: none; }}
    QListWidget#templates {{ color: #e7e3db; }}
    QListWidget#templates::item {{ color: #d7d2c9; border-radius: 9px; padding: 10px 11px; margin: 2px 0; }}
    QListWidget#templates::item:hover {{ background: #34322f; color: #f6f3ed; }}
    QListWidget#templates::item:selected {{ background: {p['accent']}; color: #fbf8f2; }}
    QListWidget#preview::item {{
        background: transparent; border-bottom: 1px solid {p['line']}; padding: 9px 6px;
    }}
    QListWidget#preview::item:last {{ border-bottom: none; }}
    QPushButton {{
        min-height: 42px; border: 1px solid {p['line']}; border-radius: 10px;
        padding: 0 15px; background: {p['surface']}; font-weight: 680;
    }}
    QPushButton:hover {{ background: #eeeae1; }}
    QPushButton:pressed {{ background: #e3ded4; }}
    QPushButton:focus {{ border: 2px solid {p['accent']}; }}
    QPushButton:disabled {{ color: #aaa59d; background: #e9e5dc; border-color: #ddd8cf; }}
    QPushButton#primary {{ background: {p['accent']}; color: #fbf8f2; border-color: {p['accent']}; }}
    QPushButton#primary:hover {{ background: {p['accent_hover']}; border-color: {p['accent_hover']}; }}
    QPushButton#stop {{ background: {p['ink']}; color: #f5f1e9; border-color: {p['ink']}; }}
    QPushButton#danger {{ color: #ef9eaa; background: transparent; border-color: #55504b; }}
    QPushButton#railAction {{ color: #ece8df; background: #34322f; border-color: #4b4843; }}
    QPushButton#railAction:hover {{ background: #403d39; }}
    QPushButton#mode {{ min-height: 38px; background: transparent; color: {p['muted']}; }}
    QPushButton#mode:checked {{ background: {p['ink']}; color: {p['surface']}; border-color: {p['ink']}; }}
    QSlider::groove:horizontal {{ height: 5px; background: #ccc6bc; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 18px; margin: -7px 0; border-radius: 9px;
        background: {p['surface']}; border: 2px solid {p['accent']};
    }}
    QCheckBox {{ spacing: 10px; padding: 4px 0; }}
    QCheckBox::indicator {{
        width: 19px; height: 19px; border: 1px solid #aaa49a; border-radius: 6px;
        background: {p['surface']};
    }}
    QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
    QSplitter::handle {{ background: transparent; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ width: 8px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: #bbb5ab; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
