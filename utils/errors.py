"""Unified error response helpers for AJAX and page requests, plus safe error utilities."""

import logging

from flask import request, flash, redirect, url_for, jsonify

_log = logging.getLogger('contract_tool')


def wants_json():
    """Detect whether the current request expects a JSON response."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in (request.headers.get('Accept') or '')
        or request.path.startswith('/api/')
    )


def api_error(message, status_code=400):
    """Return a JSON error response for AJAX/API requests."""
    response = jsonify({'success': False, 'error': message})
    response.status_code = status_code
    return response


def page_error(message, fallback_endpoint='index', status_code=400):
    """Flash an error and redirect for normal page requests."""
    flash(message, 'error')
    return redirect(url_for(fallback_endpoint))


def respond_error(message, status_code=400, fallback_endpoint='index'):
    """Unified error response — picks JSON or page based on request type."""
    if wants_json():
        return api_error(message, status_code)
    return page_error(message, fallback_endpoint, status_code)


# ── 安全错误消息 ──
# 对外仅返回通用提示，完整异常信息写入日志

GENERIC_ERROR = '操作失败，请稍后重试或联系管理员'
GENERIC_FILE_ERROR = '文件操作失败，请检查文件是否有效'
GENERIC_PARSE_ERROR = '文档解析失败，请确认文件格式正确'
GENERIC_TEMPLATE_ERROR = '模板操作失败'
GENERIC_DB_ERROR = '数据库操作失败'
GENERIC_GENERATE_ERROR = '合同生成失败，请检查模板和填写内容'


def safe_error(exc=None, log_msg='', status_code=400):
    if exc is not None:
        _log.error('%s: %s', log_msg, exc, exc_info=True)
    return GENERIC_ERROR, status_code


def safe_file_error(exc=None, log_msg='', status_code=400):
    if exc is not None:
        _log.error('%s: %s', log_msg, exc, exc_info=True)
    return GENERIC_FILE_ERROR, status_code


def safe_parse_error(exc=None, log_msg='', status_code=400):
    if exc is not None:
        _log.error('%s: %s', log_msg, exc, exc_info=True)
    return GENERIC_PARSE_ERROR, status_code
