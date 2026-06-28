"""Startup helpers for the desktop Flask entry point."""

import os
import threading
import webbrowser

from utils.logger import get_logger


def should_open_browser(no_browser, debug, environ=None):
    if no_browser:
        return False

    environ = os.environ if environ is None else environ
    is_reloader = environ.get('WERKZEUG_RUN_MAIN') == 'true'
    return is_reloader or not debug


def open_browser_later(url, delay=1.0):
    def opener():
        try:
            webbrowser.open(url)
        except Exception:
            get_logger().debug('自动打开浏览器失败', exc_info=True)

    threading.Timer(delay, opener).start()
