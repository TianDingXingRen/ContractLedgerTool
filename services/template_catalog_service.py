"""Application services for browsing, editing, and previewing templates."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import ledger_store
import template_def
from services.contract_editor_service import build_draft_revision
from services.contract_preview_service import editor_preview_model
from services.office_parse_service import generate_docx_isolated
from runtime.flask_paths import current_runtime_paths
from utils.generation_utils import prepare_generation_values
from utils.logger import get_logger
from utils.session_store import save_session_data
from utils.template_paths import safe_template_path, safe_uploaded_docx_path


DOCX_MIMETYPE = (
    'application/vnd.openxmlformats-officedocument.'
    'wordprocessingml.document'
)


class TemplateFileMissing(FileNotFoundError):
    def __init__(self, requested_name):
        super().__init__(f'模板文件不存在: {requested_name}')
        self.requested_name = requested_name


class TemplateLoadFailed(RuntimeError):
    def __init__(self, cause):
        super().__init__('Template loading failed')
        self.cause = cause


class TemplateSourcePathRejected(ValueError):
    def __init__(self, cause):
        super().__init__(str(cause))
        self.cause = cause


class TemplatePreviewRejected(ValueError):
    """Submitted preview values failed business validation."""


class TemplatePreviewGenerationFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class TemplateEditorView:
    session_id: str
    fields: list
    template_name: str
    template_filename: str
    template_revision: str
    draft_scope: str
    preview_blocks: list
    preview_warnings: list
    project_names: list


@dataclass(frozen=True)
class TemplatePreviewArtifact:
    path: str
    download_name: str
    mimetype: str = DOCX_MIMETYPE


def list_template_summaries(category_filter=''):
    templates = template_def.list_templates()
    category_filter = str(category_filter or '').strip()
    if category_filter:
        return [
            item for item in templates
            if item.get('category', '') == category_filter
        ]
    return templates


def open_template_editor(name):
    paths = current_runtime_paths()
    path = safe_template_path(name, paths)
    if not os.path.exists(path):
        raise TemplateFileMissing(name)
    definition = _load_template(path)

    session_id = str(uuid.uuid4())
    save_session_data(
        session_id,
        {
            'template_name': definition.name,
            'template_path': path,
            'template_filename': os.path.basename(path),
            'stored_name': definition.data.get('source_docx', ''),
            'step': 'editor',
        },
        paths,
    )

    fields = definition.data['fields']
    template_def.normalize_field_ids(fields)
    preview_model = editor_preview_model(
        definition.data.get('source_docx', ''),
        fields,
        paths,
    )
    return TemplateEditorView(
        session_id=session_id,
        fields=fields,
        template_name=definition.name,
        template_filename=os.path.basename(path),
        template_revision=build_draft_revision(path, fields),
        draft_scope='template::',
        preview_blocks=preview_model.get('blocks', []),
        preview_warnings=preview_model.get('warnings', []),
        project_names=ledger_store.list_project_names(),
    )


def generate_template_preview(name, submitted_values):
    paths = current_runtime_paths()
    path = safe_template_path(name, paths)
    if not os.path.exists(path):
        raise TemplateFileMissing(name)
    definition = _load_template(path)
    fields = definition.data.get('fields', [])
    field_values, input_errors = prepare_generation_values(
        fields,
        submitted_values,
    )
    if input_errors:
        raise TemplatePreviewRejected('\n'.join(input_errors))

    source_docx = definition.data.get('source_docx', '')
    source_path = ''
    if source_docx:
        try:
            source_path = safe_uploaded_docx_path(
                source_docx,
                paths,
            )
        except ValueError as exc:
            raise TemplateSourcePathRejected(exc) from exc

    output_path = os.path.join(
        str(paths.output_dir),
        f'preview_{uuid.uuid4().hex[:8]}.docx',
    )
    generation_errors, output_path = generate_docx_isolated(
        definition.data,
        fields,
        field_values,
        source_path,
        output_path,
    )
    if generation_errors:
        raise TemplatePreviewGenerationFailed(
            '预览生成失败：\n' + '\n'.join(generation_errors)
        )
    return TemplatePreviewArtifact(
        path=output_path,
        download_name=f'{definition.name}_预览.docx',
    )


def delete_template(filename):
    return template_def.delete_template(os.path.basename(filename))


def copy_template(filename):
    new_filename = template_def.copy_template(filename)
    if new_filename:
        get_logger().info(
            'Copied template %s -> %s',
            filename,
            new_filename,
        )
    return new_filename


def _load_template(path):
    try:
        return template_def.TemplateDef.load(path)
    except Exception as exc:
        raise TemplateLoadFailed(exc) from exc
