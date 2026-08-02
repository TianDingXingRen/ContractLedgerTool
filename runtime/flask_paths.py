"""Access the immutable paths attached to the active Flask application."""

from __future__ import annotations

from flask import current_app

from runtime.paths import RuntimePaths


def current_runtime_paths() -> RuntimePaths:
    """Return the active app's frozen :class:`RuntimePaths` instance."""
    paths = current_app.extensions.get('runtime_paths')
    if not isinstance(paths, RuntimePaths):
        raise RuntimeError('当前 Flask 应用未配置 RuntimePaths')
    return paths
