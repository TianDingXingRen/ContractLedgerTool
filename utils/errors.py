"""Unified error response helpers for AJAX and page requests."""

from flask import request, flash, redirect, url_for, jsonify


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
