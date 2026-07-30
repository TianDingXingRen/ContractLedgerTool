"""Read model assembly for the contract editor."""

from __future__ import annotations

import ledger_store
import template_def
from services.contract_preview_service import editor_preview_model
from utils.logger import get_logger
from utils.template_paths import template_path_from_session


def build_editor_model(session_data, runtime_paths):
    """Build the editor view model without exposing storage to the route."""
    fields = session_data.get('fields', [])
    for index, field in enumerate(fields):
        if 'id' not in field:
            field['id'] = index

    source_docx = (
        session_data.get('stored_name')
        or session_data.get('source_docx', '')
    )
    if not source_docx:
        template_path = template_path_from_session(
            session_data,
            runtime_paths,
        )
        if template_path:
            try:
                source_docx = template_def.TemplateDef.load(
                    template_path
                ).data.get('source_docx', '')
            except Exception:
                get_logger().warning(
                    'Failed to resolve editor source document from %s',
                    template_path,
                    exc_info=True,
                )
                source_docx = ''

    preview_model = editor_preview_model(
        source_docx,
        fields,
        runtime_paths,
    )
    return {
        'fields': fields,
        'field_count': len(fields),
        'template_name': session_data.get('template_name', '未命名'),
        'template_filename': session_data.get('template_filename', ''),
        'preview_blocks': preview_model.get('blocks', []),
        'preview_warnings': preview_model.get('warnings', []),
        'project_names': ledger_store.list_project_names(),
        'classification_project_name': session_data.get(
            'project_name',
            '',
        ),
        'batch_allowed': not bool(
            session_data.get('procurement_data_sheet_id')
        ),
    }
