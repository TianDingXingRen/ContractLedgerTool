"""Runtime-scoped template and upload path helpers."""

from __future__ import annotations

import os
from typing import Any

from runtime.paths import RuntimePaths
from utils.security import path_within, safe_join_file


def safe_uploaded_docx_path(filename: str, paths: RuntimePaths) -> str:
    return safe_join_file(
        str(paths.uploads_dir),
        filename,
        allowed_ext={'.docx'},
    )


def safe_template_path(name: str, paths: RuntimePaths) -> str:
    filename = os.path.basename(name or '')
    if not filename.endswith('.contract-template'):
        raise ValueError('模板文件名无效')
    return safe_join_file(
        str(paths.templates_dir),
        filename,
        allowed_ext={'.contract-template'},
    )


def validate_stored_docx(filename: str, paths: RuntimePaths) -> str:
    if not filename:
        return ''
    path = safe_uploaded_docx_path(filename, paths)
    if not os.path.isfile(path):
        raise ValueError('模板源文件不存在')
    return os.path.basename(filename)


def template_path_from_session(
    data: dict[str, Any],
    paths: RuntimePaths,
) -> str:
    template_path_data = data.get('template_path', '')
    if template_path_data:
        path = os.path.abspath(template_path_data)
        if path_within(str(paths.templates_dir), path) and os.path.exists(path):
            return path

    template_filename = data.get('template_filename', '')
    if template_filename:
        try:
            path = safe_template_path(template_filename, paths)
        except ValueError:
            return ''
        if os.path.exists(path):
            return path
    return ''
