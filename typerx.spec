from PyInstaller.utils.hooks import collect_all, collect_data_files

qt_datas = collect_data_files("PySide6")
interception_datas, interception_binaries, interception_hidden = collect_all("interception")

hiddenimports = interception_hidden + [
    "win32api",
    "win32con",
    "win32gui",
    "pywintypes",
    "pythoncom",
]

a = Analysis(
    ["src/typerx/__main__.py"],
    pathex=["src"],
    binaries=interception_binaries,
    datas=qt_datas + interception_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TyperX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
