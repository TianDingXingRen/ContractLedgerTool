"""Shared helpers for editor-side contract preview metadata."""

from __future__ import annotations

from typing import Any

from services.office_parse_service import build_preview_model_isolated
from utils.logger import get_logger
from utils.template_paths import safe_uploaded_docx_path


def editor_preview_model(
    source_docx: str,
    fields: list[dict[str, Any]],
    paths,
) -> dict[str, Any]:
    """Resolve an uploaded source DOCX and return a safe editor preview model."""
    if not source_docx:
        return {
            'blocks': [],
            'warnings': ['模板未记录源 DOCX，已切换为字段预览。'],
        }
    try:
        source_path = safe_uploaded_docx_path(source_docx, paths)
    except Exception:
        get_logger().warning('Failed to resolve preview source DOCX: %s', source_docx, exc_info=True)
        return {
            'blocks': [],
            'warnings': ['模板源文件路径无效，已切换为字段预览。'],
        }
    return build_preview_model_isolated(source_path, fields)
