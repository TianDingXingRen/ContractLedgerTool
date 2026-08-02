"""Startup helpers for the desktop Flask entry point."""

import ipaddress
import os
import threading
import webbrowser

from utils.logger import get_logger


def is_loopback_host(host):
    """Return whether a bind host is restricted to the local machine."""
    value = str(host or '').strip().lower()
    if value == 'localhost':
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def validate_bind_host(
    host,
    allow_remote=False,
    remote_token='',
    tls_cert='',
    tls_key='',
    debug=False,
):
    """Reject accidental network exposure unless explicitly enabled."""
    if is_loopback_host(host):
        return host
    if not allow_remote:
        raise ValueError(
            '为保护本地合同数据，默认仅允许监听 127.0.0.1/::1；'
            '如确需局域网访问，请显式设置 CT_ALLOW_REMOTE=1'
        )
    if debug:
        raise ValueError('局域网访问时禁止启用 CT_DEBUG')
    if len(str(remote_token or '')) < 16:
        raise ValueError(
            '局域网访问必须设置至少 16 位的 CT_REMOTE_ACCESS_TOKEN，'
            '浏览器登录时将该令牌作为密码使用'
        )
    if not tls_cert or not tls_key:
        raise ValueError(
            '局域网访问必须同时设置 CT_REMOTE_TLS_CERT 和 CT_REMOTE_TLS_KEY，'
            '禁止通过明文 HTTP 传输访问令牌和合同数据'
        )
    for label, path in (
        ('CT_REMOTE_TLS_CERT', tls_cert),
        ('CT_REMOTE_TLS_KEY', tls_key),
    ):
        if not os.path.isfile(os.path.abspath(path)):
            raise ValueError(f'{label} 指向的文件不存在')
    return host


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
