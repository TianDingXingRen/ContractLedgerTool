"""Flask request/response hooks for security and rate limiting."""

from __future__ import annotations

import threading
import time
import re
import uuid
from collections import OrderedDict

from flask import Response, abort, g, request, session

from utils.errors import api_error, wants_json
from utils.logger import reset_request_id, set_request_id
from utils.security import hmac_compare
from core.maintenance_gate import maintenance_gate
from core.app_startup import is_loopback_host


_rate_limit_store_path = OrderedDict()
_rate_limit_store_global = OrderedDict()
_rate_limit_lock_path = threading.Lock()
_rate_limit_lock_global = threading.Lock()
_RATE_LIMIT_MAX_KEYS = 10000
_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9._-]{8,64}$')


def _safe_request_id(value):
    value = str(value or '').strip()
    if _REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex


def reset_rate_limit_state():
    """Clear in-memory rate-limit buckets between isolated app instances."""
    with _rate_limit_lock_global:
        _rate_limit_store_global.clear()
    with _rate_limit_lock_path:
        _rate_limit_store_path.clear()


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

    if app.testing:
        reset_rate_limit_state()
        maintenance_gate.reset()

    @app.before_request
    def _enter_request_gate():
        token, context_token = maintenance_gate.enter_request()
        g.maintenance_gate_token = token
        g.maintenance_gate_context_token = context_token

    @app.before_request
    def _attach_request_context():
        request_id = _safe_request_id(request.headers.get('X-Request-ID'))
        g.request_id = request_id
        g.request_id_token = set_request_id(request_id)

    @app.before_request
    def _protect_remote_access():
        if is_loopback_host(request.remote_addr or ''):
            return None
        expected = str(getattr(config, 'REMOTE_ACCESS_TOKEN', '') or '')
        authorization = request.authorization
        provided = request.headers.get('X-Contract-Tool-Token', '')
        if not provided and authorization and authorization.type.lower() == 'basic':
            provided = authorization.password or ''
        if expected and hmac_compare(expected, provided):
            return None
        return Response(
            'Remote authentication required', status=401,
            headers={'WWW-Authenticate': 'Basic realm="Contract Ledger Tool"'},
        )

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
        response.headers['X-Request-ID'] = g.get('request_id', '-')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.endpoint == 'static':
            # Official templates append a per-file version token. Versioned
            # assets are immutable; direct, unversioned probes get a short
            # cache to avoid stale resources after an upgrade.
            if request.args.get('v'):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            else:
                response.headers['Cache-Control'] = 'public, max-age=3600'
        else:
            response.headers['Cache-Control'] = 'no-store, max-age=0'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'"
        )
        return response

    @app.teardown_request
    def _release_request_context(_error=None):
        gate_token = g.pop('maintenance_gate_token', None)
        gate_context_token = g.pop('maintenance_gate_context_token', None)
        if gate_token is not None and gate_context_token is not None:
            maintenance_gate.leave_request(gate_token, gate_context_token)
        request_id_token = g.pop('request_id_token', None)
        if request_id_token is not None:
            reset_request_id(request_id_token)
