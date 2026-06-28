# -*- coding: utf-8 -*-
"""Optional browser-side smoke tests.

These run when Playwright and its browser binaries are installed. The regular
unit suite skips them automatically on lightweight environments.
"""

import threading
import unittest

from werkzeug.serving import make_server

import app

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None


class BrowserUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest('Playwright is not installed')
        cls.server = make_server('127.0.0.1', 0, app.app)
        cls.base_url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'server'):
            cls.server.shutdown()
        if hasattr(cls, 'thread'):
            cls.thread.join(timeout=5)

    def test_operations_pages_render_in_browser(self):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 800})
                page.goto(f'{self.base_url}/diagnostics', wait_until='networkidle')
                page.locator('[data-testid="copy-diagnostics"]').wait_for()
                page.locator('[data-testid="refresh-diagnostics"]').wait_for()

                page.goto(f'{self.base_url}/backups', wait_until='networkidle')
                page.locator('[data-testid="create-backup"]').wait_for()
                browser.close()
        except Exception as exc:
            if 'Executable doesn' in str(exc) or 'playwright install' in str(exc):
                self.skipTest('Playwright browser binaries are not installed')
            raise


if __name__ == '__main__':
    unittest.main()
