"""Flask error handlers for page and API responses."""

from __future__ import annotations

import threading

from flask import render_template
from werkzeug.exceptions import HTTPException, SecurityError

from core.domain_errors import DomainError
from utils.errors import api_error, wants_json
from utils.logger import get_logger


def register_error_handlers(app):
    """Register global error handlers on the Flask app."""

    @app.errorhandler(400)
    def handle_400(e):
        if isinstance(e, SecurityError):
            # Host validation can fail before Flask creates a URL adapter.
            # Rendering the normal template would call url_for() and mask the
            # intended 400 response with a secondary exception.
            return '请求主机不受信任', 400
        msg = getattr(e, 'description', None) or '请求参数无效'
        if wants_json():
            return api_error(str(msg), 400)
        return render_template('error.html', code=400, message=str(msg)), 400

    @app.errorhandler(404)
    def handle_404(e):
        msg = getattr(e, 'description', None) or '页面未找到'
        if wants_json():
            return api_error(str(msg), 404)
        return render_template('error.html', code=404, message=str(msg)), 404

    @app.errorhandler(429)
    def handle_429(e):
        msg = getattr(e, 'description', None) or '请求过于频繁'
        if wants_json():
            return api_error(str(msg), 429)
        return render_template('error.html', code=429, message=str(msg)), 429

    @app.errorhandler(500)
    def handle_500(e):
        get_logger().error('Internal server error: %s', e, exc_info=True)
        if wants_json():
            return api_error('服务器内部错误', 500)
        return render_template('error.html', code=500, message='服务器内部错误，请稍后再试'), 500

    error_handler_guard = threading.local()

    @app.errorhandler(Exception)
    def handle_unhandled(e):
        if isinstance(e, HTTPException):
            code = int(e.code or 500)
            message = str(e.description or e.name or '请求处理失败')
            if wants_json():
                return api_error(message, code)
            return render_template('error.html', code=code, message=message), code
        if getattr(error_handler_guard, 'active', False):
            return '500 Internal Server Error', 500
        error_handler_guard.active = True
        try:
            get_logger().error('Unhandled exception: %s', e, exc_info=True)
            if wants_json():
                return api_error('服务器内部错误', 500)
            return render_template('error.html', code=500, message='服务器内部错误，请稍后再试'), 500
        finally:
            error_handler_guard.active = False
    @app.errorhandler(DomainError)
    def handle_domain_error(e):
        code = int(e.status_code or 400)
        if wants_json():
            return api_error(e.public_message, code)
        return render_template('error.html', code=code, message=e.public_message), code
