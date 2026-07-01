"""Flask request/response hooks for security and rate limiting."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

from flask import abort, request, session

from utils.errors import api_error, wants_json
from utils.security import hmac_compare


_rate_limit_store_path = OrderedDict()
_rate_limit_store_global = OrderedDict()
_rate_limit_lock_path = threading.Lock()
_rate_limit_lock_global = threading.Lock()
_RATE_LIMIT_MAX_KEYS = 10000


def _check_single_limit(store, lock, key, max_req, window, now):
    """Check one rate-limit bucket and return (allowed, retry_seconds)."""
    with lock:
        while len(store) >= _RATE_LIMIT_MAX_KEYS:
            store.popitem(last=False)
        timestamps = store.get(key, [])
        timestamps[:] = [t for t in timestamps if t > now - window]
        if len(timestamps) >= max_req:
            retry = int(timestamps[0] + window - now) + 1
            return False, retry
        timestamps.append(now)
        store[key] = timestamps
        store.move_to_end(key)
    return True, 0


def _check_rate_limit(config):
    """Run global-IP and path-level rate limits."""
    path = request.path
    max_req, window = config.RATE_LIMITS.get(path, config.RATE_LIMIT_DEFAULT)
    ip = request.remote_addr or '127.0.0.1'
    now = time.time()

    if ip in ('127.0.0.1', '::1', 'localhost'):
        global_max, global_window = config.RATE_LIMIT_LOCALHOST
    else:
        global_max, global_window = config.RATE_LIMIT_GLOBAL
    global_allowed, global_retry = _check_single_limit(
        _rate_limit_store_global, _rate_limit_lock_global,
        ip, global_max, global_window, now,
    )
    if not global_allowed:
        return False, global_retry

    return _check_single_limit(
        _rate_limit_store_path, _rate_limit_lock_path,
        f'{ip}:{path}', max_req, window, now,
    )


def register_security_hooks(app, config):
    """Register CSRF/rate-limit request guards and security response headers."""

    @app.before_request
    def _protect_post_requests():
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            expected = session.get('_csrf_token')
            provided = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not expected or not provided or not hmac_compare(expected, provided):
                abort(400, description='CSRF token missing or invalid')
            allowed, retry = _check_rate_limit(config)
            if not allowed:
                if wants_json():
                    return api_error('请求过于频繁，请稍后再试', 429)
                abort(429, description=f'请求过于频繁，请 {retry} 秒后再试')
        return None

    @app.after_request
    def _add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'"
        )
        return response
