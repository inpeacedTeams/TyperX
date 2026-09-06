from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

from typerx.ai_runtime import Runtime
from typerx.platform.windows import GlobalHotkeys


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root.resolve()

    def interceptRequest(self, info):
        url = info.requestUrl()
        allowed = url.toString() == "qrc:///qtwebchannel/qwebchannel.js"
        if url.isLocalFile():
            allowed = Path(url.toLocalFile()).resolve().parent == self.root
        info.block(not allowed)


class LocalPage(QWebEnginePage):
    def __init__(self, profile, index, parent):
        super().__init__(profile, parent)
        self.index = index

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return is_main_frame and url == self.index

    def createWindow(self, window_type):
        return None


class Bridge(QObject):
    response = Signal(str)
    hotkey_start = Signal()

    def __init__(self, root, parent):
        super().__init__(parent)
        self.runtime = Runtime(root, lambda event: self.response.emit(json.dumps(event, ensure_ascii=False)))
        self.hotkey_start.connect(lambda: self.runtime.submit("hotkey", "start", {}))

    @Slot(str)
    def request(self, payload):
        if len(payload) > 220000:
            return
        try:
            value = json.loads(payload)
            if not isinstance(value.get("data", {}), dict):
                return
            self.runtime.submit(str(value["id"])[:80], str(value["operation"])[:40], value.get("data", {}))
        except (ValueError, KeyError, TypeError):
            return

    @Slot()
    def stop(self):
        self.runtime.stop()


class WebWindow(QWebEngineView):
    def __init__(self, store):
        super().__init__()
        self.setWindowTitle("TyperX · AI Studio")
        self.resize(1240, 840)
        self.setMinimumSize(760, 620)
        root = Path(__file__).with_name("web")
        self.profile = QWebEngineProfile(self)  # Off-the-record browser profile.
        self.interceptor = LocalOnly(root, self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        index = QUrl.fromLocalFile(str(root / "index.html"))
        self.local_page = LocalPage(self.profile, index, self)
        self.setPage(self.local_page)
        self.bridge = Bridge(store.data_dir, self)
        self.bridge.runtime.own_window = int(self.winId())
        self.channel = QWebChannel(self.local_page)
        self.channel.registerObject("studio", self.bridge)
        self.local_page.setWebChannel(self.channel)
        self.hotkeys = GlobalHotkeys(self.bridge.hotkey_start.emit, self.bridge.runtime.stop)
        self.hotkeys.start()
        self.load(index)

    def closeEvent(self, event):
        self.hotkeys.close()
        self.bridge.runtime.close()
        super().closeEvent(event)
