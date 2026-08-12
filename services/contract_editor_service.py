"""Read model assembly for the contract editor."""

from __future__ import annotations

import hashlib
import json

import ledger_store
import template_def
from services.contract_preview_service import editor_preview_model
from utils.file_digest import sha256_file
from utils.logger import get_logger
from utils.template_paths import template_path_from_session


def build_draft_revision(template_path, fields):
    """Return a stable content revision for browser-draft isolation."""
    if template_path:
        try:
            return sha256_file(template_path)
        except OSError:
            get_logger().warning(
                'Failed to hash editor template %s',
                template_path,
                exc_info=True,
            )
    canonical_fields = json.dumps(
        fields or [],
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        default=str,
    )
    return hashlib.sha256(canonical_fields.encode('utf-8')).hexdigest()


def build_draft_scope(session_data):
    """Keep procurement/project drafts out of unrelated editor sessions."""
    source_type = str(session_data.get('source_type') or 'template')
    project_id = (
        session_data.get('source_project_id')
        or session_data.get('procurement_project_id')
        or ''
    )
    source_id = (
        session_data.get('procurement_data_sheet_id')
        or session_data.get('source_id')
        or ''
    )
    return ':'.join((source_type, str(project_id), str(source_id)))


def build_editor_model(session_data, runtime_paths):
    """Build the editor view model without exposing storage to the route."""
    fields = session_data.get('fields', [])
    template_def.normalize_field_ids(fields)

    template_path = template_path_from_session(
        session_data,
        runtime_paths,
    )
    source_docx = (
        session_data.get('stored_name')
        or session_data.get('source_docx', '')
    )
    if not source_docx:
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
        'template_revision': build_draft_revision(template_path, fields),
        'draft_scope': build_draft_scope(session_data),
        'preview_blocks': preview_model.get('blocks', []),
        'preview_warnings': preview_model.get('warnings', []),
        'project_names': ledger_store.list_project_names(),
        'classification_project_name': session_data.get(
            'project_name',
            '',
        ),
        'classification_subsystem_name': session_data.get(
            'subsystem_name',
            '',
        ),
        'batch_allowed': not bool(
            session_data.get('procurement_data_sheet_id')
        ),
    }
