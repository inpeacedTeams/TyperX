"""Real Qt WebEngine/QWebChannel smoke tests, without Telegram or keyboard output.

Run on Windows with: python -m unittest discover -s tests -p test_webview_smoke.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Requires Windows and Qt WebEngine")
class WebViewSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from typerx.ui.web_window import WebWindow
        self.directory = tempfile.TemporaryDirectory()
        self.hotkey_start = patch("typerx.ui.web_window.GlobalHotkeys.start")
        self.hotkey_close = patch("typerx.ui.web_window.GlobalHotkeys.close")
        self.hotkey_start.start()
        self.hotkey_close.start()
        self.addCleanup(self.hotkey_start.stop)
        self.addCleanup(self.hotkey_close.stop)
        self.window = WebWindow(SimpleNamespace(data_dir=Path(self.directory.name)))
        self.addCleanup(self.cleanup_window)
        self.window.show()
        self.wait_js("Boolean(document.getElementById('live-preset')?.options.length)")

    def cleanup_window(self):
        self.window.close()
        self.window.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def evaluate(self, script, timeout=5):
        result = []
        self.window.page().runJavaScript(script, result.append)
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(result, "Qt did not return the JavaScript result")
        return result[0]

    def wait_js(self, expression, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(0.05)
        self.fail("Timed out waiting for: " + expression)

    def test_real_bridge_loads_and_saves_local_configuration(self):
        self.assertEqual(self.evaluate("document.getElementById('live-preset').options[0].text"), "Естественный")
        self.evaluate("document.getElementById('wpm').value='80'; save().then(()=>{window.saved=true;}).catch(e=>{window.saveError=e.message;});")
        self.wait_js("Boolean(window.saved || window.saveError)")
        self.assertTrue(self.evaluate("window.saved === true"), self.evaluate("window.saveError || ''"))
        saved = json.loads((Path(self.directory.name) / "ai.json").read_text("utf-8"))
        self.assertEqual(saved["wpm"], 80)
        self.assertNotIn("api_key", saved)

    def test_navigation_and_error_display(self):
        for section in ["telegram", "llm", "presets", "manual", "live"]:
            self.evaluate(f"document.querySelector('[data-view={section}]').click()")
            self.assertTrue(self.evaluate(f"!document.getElementById('view-{section}').hidden"))
        self.evaluate("document.getElementById('prepare').click()")
        self.wait_js("document.getElementById('notice').classList.contains('error')")
        self.assertIn("личного чата", self.evaluate("document.getElementById('notice').textContent"))
        self.assertTrue(self.window.bridge.runtime.stopped.is_set())

    def test_malformed_bridge_messages_are_rejected(self):
        responses = []
        self.window.bridge.response.connect(responses.append)
        for payload in ["[]", "null", "broken", '{"id":"test","operation":5}']:
            self.window.bridge.request(payload)
        self.assertEqual(len(responses), 4)
        self.assertTrue(all(not json.loads(value)["ok"] for value in responses))

    def test_network_requests_are_blocked(self):
        from PySide6.QtCore import QUrl
        class Request:
            blocked = False
            def requestUrl(self):
                return QUrl("https://example.com/exfiltrate")
            def block(self, value):
                self.blocked = value
        request = Request()
        self.window.interceptor.interceptRequest(request)
        self.assertTrue(request.blocked)
        self.assertFalse(self.window.local_page.acceptNavigationRequest(QUrl("https://example.com"), None, True))


if __name__ == "__main__":
    unittest.main()
