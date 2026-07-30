"""Application services for creating templates from uploaded Word files."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass

import template_def
from services.legacy_doc_conversion_service import convert_doc_to_docx
from services.office_parse_service import detect_markers_isolated
from runtime.flask_paths import current_runtime_paths
from utils.generation_utils import validate_template_source_bindings
from utils.logger import get_logger
from utils.security import limit_text, validate_office_archive
from utils.session_store import load_session_data, save_session_data
from utils.template_paths import safe_uploaded_docx_path, validate_stored_docx


ALLOWED_EXTENSIONS = {'docx', 'doc'}
DOC_CONVERT_TIMEOUT = 30


class TemplateUploadRejected(ValueError):
    """The uploaded file cannot be accepted as a template source."""


class TemplateMarkerDetectionFailed(RuntimeError):
    """Marker extraction failed after the source file was stored."""

    def __init__(self, cause):
        super().__init__('DOCX placeholder detection failed')
        self.cause = cause


@dataclass(frozen=True)
class ManualTemplateResult:
    filename: str
    session_id: str


def load_style_context(session_id):
    data = load_session_data(session_id, current_runtime_paths())
    return {
        'stored_name': data.get('stored_name', ''),
        'raw_name': data.get('raw_name', ''),
        'detected_fields': data.get('detected_fields', []),
    }


def upload_template_style(file_stream, raw_name):
    extension = _validated_extension(raw_name)
    paths = current_runtime_paths()
    session_id = str(uuid.uuid4())
    stored_name = (
        f'{session_id}.doc' if extension == 'doc'
        else f'{session_id}.docx'
    )
    upload_path = os.path.join(str(paths.uploads_dir), stored_name)
    with open(upload_path, 'wb') as target:
        shutil.copyfileobj(file_stream, target)

    if extension == 'doc':
        converted = _convert_doc(upload_path)
        if not converted or not _is_valid_docx(converted):
            _remove_file(upload_path)
            raise TemplateUploadRejected(
                '无法将 .doc 转换为 .docx，请用 Word/WPS 打开文件后'
                '另存为 .docx 格式再上传'
            )
        _remove_file(upload_path)
        stored_name = f'{session_id}.docx'
        upload_path = os.path.join(str(paths.uploads_dir), stored_name)
        get_logger().info('DOC converted successfully')

    if not _is_valid_docx(upload_path):
        _remove_file(upload_path)
        raise TemplateUploadRejected(
            '文件不是有效的 DOCX 格式（需为 ZIP 压缩的 Office 文档）'
        )

    try:
        detected_fields = detect_markers_isolated(upload_path)
    except Exception as exc:
        _remove_uploaded_file(stored_name)
        raise TemplateMarkerDetectionFailed(exc) from exc

    save_session_data(
        session_id,
        {
            'raw_name': raw_name,
            'stored_name': stored_name,
            'detected_fields': detected_fields,
        },
        paths,
    )
    return session_id


def create_manual_template(
    template_name,
    category,
    stored_name,
    fields,
):
    template_name = str(template_name or '').strip()
    if not template_name:
        raise ValueError('模板名称不能为空')
    if len(template_name) > 120:
        raise ValueError('模板名称不能超过120个字符')
    template_name = limit_text(template_name, 120)
    category = limit_text(str(category or '').strip(), 50)
    paths = current_runtime_paths()
    stored_name = validate_stored_docx(
        str(stored_name or '').strip(),
        paths,
    )

    definition = template_def.TemplateDef.create(
        template_name,
        stored_name,
        fields,
    )
    if category:
        definition.data['category'] = category
    try:
        definition.validate()
    except template_def.TemplateValidationError as exc:
        raise ValueError(f'模板数据验证失败：{exc}') from exc

    if stored_name:
        binding_errors = validate_template_source_bindings(
            fields,
            safe_uploaded_docx_path(stored_name, paths),
        )
        if binding_errors:
            raise ValueError(
                '模板预检失败：\n' + '\n'.join(binding_errors)
            )

    path = definition.save()
    session_id = str(uuid.uuid4())
    save_session_data(
        session_id,
        {
            'template_name': template_name,
            'template_path': path,
            'template_filename': os.path.basename(path),
            'stored_name': stored_name,
            'step': 'editor',
        },
        paths,
    )
    return ManualTemplateResult(
        filename=os.path.basename(path),
        session_id=session_id,
    )


def _validated_extension(raw_name):
    raw_name = str(raw_name or '')
    if '.' not in raw_name:
        raise TemplateUploadRejected(
            '请上传 .docx 或 .doc 格式的文档'
        )
    extension = raw_name.rsplit('.', 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise TemplateUploadRejected('仅支持 .docx 和 .doc 格式')
    return extension


def _is_valid_docx(filepath):
    try:
        validate_office_archive(filepath)
        return True
    except Exception:
        get_logger().debug(
            'DOCX header validation failed',
            exc_info=True,
        )
        return False


def _convert_doc(doc_path):
    target = doc_path.rsplit('.', 1)[0] + '.docx'
    try:
        return convert_doc_to_docx(
            doc_path,
            target,
            timeout=DOC_CONVERT_TIMEOUT,
        )
    except Exception:
        get_logger().warning('.doc 转换失败', exc_info=True)
        return None


def _remove_uploaded_file(stored_name):
    path = safe_uploaded_docx_path(
        os.path.basename(stored_name),
        current_runtime_paths(),
    )
    _remove_file(path)


def _remove_file(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        get_logger().debug('Template upload already removed')
