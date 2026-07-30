"""Application service for persisting template default values."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import field_eval
import template_def
from runtime.flask_paths import current_runtime_paths
from utils.errors import GENERIC_TEMPLATE_ERROR
from utils.field_utils import (
    filter_table_rows,
    normalize_number_field_value,
    normalize_table_columns,
)
from utils.generation_utils import validate_template_source_bindings
from utils.logger import get_logger
from utils.security import MAX_TABLE_ROWS, limit_text
from utils.session_store import load_session_data
from utils.template_paths import (
    safe_uploaded_docx_path,
    template_path_from_session,
)


class TemplateDefaultsSessionExpired(ValueError):
    pass


class TemplateDefaultsFileMissing(FileNotFoundError):
    pass


class TemplateDefaultsRejected(ValueError):
    pass


class TemplateDefaultsOperationFailed(RuntimeError):
    def __init__(self, cause):
        super().__init__(GENERIC_TEMPLATE_ERROR)
        self.cause = cause


@dataclass(frozen=True)
class TemplateDefaultsResult:
    warnings: list


def save_template_defaults(session_id, submitted_values):
    paths = current_runtime_paths()
    try:
        session_data = load_session_data(session_id, paths)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise TemplateDefaultsSessionExpired(
            '会话已失效，请重新选择模板'
        ) from exc

    template_path = template_path_from_session(
        session_data,
        paths,
    )
    if not template_path or not os.path.exists(template_path):
        raise TemplateDefaultsFileMissing('模板文件不存在')

    try:
        definition = template_def.TemplateDef.load(template_path)
    except Exception as exc:
        get_logger().error(
            '模板加载失败: %s',
            exc,
            exc_info=True,
        )
        raise TemplateDefaultsOperationFailed(exc) from exc

    fields = definition.data.get('fields', [])
    errors = []
    for index, field in enumerate(fields):
        _apply_field_default(
            field,
            index,
            submitted_values,
            errors,
        )
    if errors:
        raise TemplateDefaultsRejected('\n'.join(errors))

    warnings = _binding_warnings(definition, fields, paths)
    try:
        definition.save(template_path)
    except Exception as exc:
        get_logger().error(
            '保存模板默认值失败: %s',
            exc,
            exc_info=True,
        )
        raise TemplateDefaultsOperationFailed(exc) from exc
    return TemplateDefaultsResult(warnings=warnings)


def _apply_field_default(field, index, submitted_values, errors):
    field_type = field.get('field_type')
    if field_type == 'table':
        _apply_table_default(
            field,
            index,
            submitted_values,
            errors,
        )
        return
    if field_type == 'calculated':
        return

    default_value = limit_text(
        submitted_values.get(f'field_{index}', '')
    )
    label = field.get('label', field.get('key'))
    if field_type == 'number' and default_value:
        try:
            default_value = normalize_number_field_value(
                default_value,
                field,
            )
        except ValueError as exc:
            errors.append(f'{label}{exc}')
    elif field_type == 'select' and default_value:
        options = [
            str(option) for option in field.get('options', [])
        ]
        if options and default_value not in options:
            errors.append(f'{label} 的预制选项无效')
    field['default_value'] = default_value


def _apply_table_default(field, index, submitted_values, errors):
    label = field.get('label', field.get('key'))
    columns_raw = submitted_values.get(
        f'table_cols_{field.get("id")}'
    )
    if columns_raw:
        try:
            submitted_columns = json.loads(columns_raw)
            field['columns'] = normalize_table_columns(
                field,
                submitted_columns,
            )
        except (json.JSONDecodeError, TypeError):
            errors.append(f'{label} 的列定义格式错误')
        except (ValueError, field_eval.FormulaError) as exc:
            errors.append(f'{label} 的列定义无效：{exc}')

    raw_value = submitted_values.get(f'field_{index}', '')
    try:
        rows = json.loads(raw_value) if raw_value else []
        if not isinstance(rows, list):
            raise ValueError('表格数据必须是数组')
        if len(rows) > MAX_TABLE_ROWS:
            raise ValueError(
                f'表格行数不能超过 {MAX_TABLE_ROWS}'
            )
        field['default_rows'] = filter_table_rows(field, rows)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f'{label} 的预制表格内容无效：{exc}')


def _binding_warnings(definition, fields, paths):
    source_docx = definition.data.get('source_docx', '')
    if not source_docx:
        return []
    try:
        docx_path = safe_uploaded_docx_path(source_docx, paths)
        warnings = validate_template_source_bindings(
            fields,
            docx_path,
        )
        if warnings:
            get_logger().warning(
                '模板默认值保存时的 binding 预警：%s',
                '; '.join(warnings),
            )
        return warnings or []
    except ValueError:
        get_logger().warning(
            '模板源文件路径无效，无法执行默认值绑定预检: %s',
            source_docx,
            exc_info=True,
        )
        return []
