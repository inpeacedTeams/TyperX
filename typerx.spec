from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

qt_datas = collect_data_files("PySide6")
interception_datas, interception_binaries, interception_hidden = collect_all("interception")

hiddenimports = interception_hidden + collect_submodules("telethon") + [
    "win32api", "win32con", "win32gui", "win32crypt", "win32process",
    "pywintypes", "pythoncom",
]

a = Analysis(
    ["src/typerx/__main__.py"],
    pathex=["src"],
    binaries=interception_binaries,
    datas=qt_datas + interception_datas + [("src/typerx/ui/web", "typerx/ui/web")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
