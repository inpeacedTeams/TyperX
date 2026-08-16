from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("PySide6")

a = Analysis(["src/typerx/__main__.py"], pathex=["src"], binaries=[], datas=datas, hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TyperX", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False, disable_windowed_traceback=False, argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None)
