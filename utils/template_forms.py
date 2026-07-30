"""Framework-neutral parsing for template field definitions."""

from __future__ import annotations

import field_eval
from utils.field_utils import (
    field_key_from_label,
    normalize_number_field_value,
    safe_col_key,
    unique_key,
)
from utils.security import (
    MAX_TABLE_COLUMNS,
    MAX_TEMPLATE_FIELDS,
    bounded_decimal_places,
    bounded_int,
    limit_text,
)


FIELD_TYPES = {
    'text',
    'number',
    'textarea',
    'select',
    'table',
    'calculated',
}
TABLE_COLUMN_TYPES = FIELD_TYPES - {'table'}


def parse_field_location(form, idx, field_type):
    if field_type == 'table':
        try:
            return {
                'type': 'table',
                'table_index': bounded_int(
                    form.get(f'field_table_index_{idx}', ''),
                    default=0,
                    label='表格位置',
                ),
                'template_row_index': bounded_int(
                    form.get(
                        f'field_template_row_index_{idx}', 1
                    ),
                    default=1,
                    label='表格模板行',
                ),
            }
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    table_cell_idx = form.get(f'field_table_index_{idx}', '')
    if table_cell_idx:
        try:
            return {
                'type': 'table_cell',
                'table_index': bounded_int(
                    table_cell_idx, label='表格位置'
                ),
                'row_index': bounded_int(
                    form.get(f'field_row_index_{idx}', 0),
                    label='行位置',
                ),
                'col_index': bounded_int(
                    form.get(f'field_col_index_{idx}', 0),
                    label='列位置',
                ),
                'placeholder': limit_text(
                    form.get(f'field_placeholder_{idx}', ''), 200
                ),
            }
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    body_index = form.get(f'field_body_index_{idx}', '')
    if body_index:
        try:
            return {
                'type': 'paragraph',
                'body_index': bounded_int(
                    body_index, label='段落位置'
                ),
                'placeholder': limit_text(
                    form.get(f'field_placeholder_{idx}', ''), 200
                ),
            }
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    return {
        'type': 'paragraph',
        'body_index': 0,
        'placeholder': '',
    }


def parse_table_columns(form, idx, label):
    columns = []
    col_idx = 0
    while True:
        if col_idx >= MAX_TABLE_COLUMNS:
            raise ValueError(
                f'{label} 的列数不能超过 {MAX_TABLE_COLUMNS}'
            )
        col_label = form.get(f'col_label_{idx}_{col_idx}')
        if col_label is None:
            break
        col_label = col_label.strip()
        if not col_label:
            col_idx += 1
            continue
        col_type = form.get(
            f'col_type_{idx}_{col_idx}', 'text'
        )
        if col_type not in TABLE_COLUMN_TYPES:
            col_type = 'text'
        col_formula = form.get(
            f'col_formula_{idx}_{col_idx}', ''
        ).strip()
        if col_type == 'calculated' and not col_formula:
            col_type = 'text'
        if col_type == 'calculated':
            try:
                field_eval.validate_formula(col_formula)
            except field_eval.FormulaError as exc:
                raise ValueError(
                    f'{col_label} 公式无效：{exc}'
                ) from exc
        col_default = limit_text(
            form.get(f'col_default_{idx}_{col_idx}', ''), 2000
        )
        column = {
            'key': safe_col_key(
                col_label,
                col_idx,
                {item['key'] for item in columns},
            ),
            'label': col_label,
            'field_type': col_type,
            'formula': (
                col_formula if col_type == 'calculated' else ''
            ),
            'default_value': (
                col_default if col_type != 'calculated' else ''
            ),
        }
        if col_type == 'select':
            options_text = form.get(
                f'col_options_{idx}_{col_idx}', ''
            )
            column['options'] = [
                limit_text(option.strip(), 200)
                for option in options_text.splitlines()
                if option.strip()
            ][:100]
        if col_type == 'number':
            try:
                column['decimal_places'] = (
                    bounded_decimal_places(
                        form.get(
                            f'col_decimal_{idx}_{col_idx}', 2
                        )
                    )
                )
                if col_default:
                    column['default_value'] = (
                        normalize_number_field_value(
                            col_default, column
                        )
                    )
            except ValueError as exc:
                raise ValueError(f'{col_label}{exc}') from exc
        columns.append(column)
        col_idx += 1
    return columns or [
        {
            'key': 'col_0',
            'label': '内容',
            'field_type': 'text',
            'formula': '',
        }
    ]


def parse_single_field(form, idx, fields_so_far):
    label = form.get(f'field_label_{idx}', '').strip()
    if not label:
        return None

    field_type = form.get(f'field_type_{idx}', 'text')
    if field_type not in FIELD_TYPES:
        field_type = 'text'
    field_formula = form.get(
        f'field_formula_{idx}', ''
    ).strip()
    if field_type == 'calculated' and not field_formula:
        field_type = 'text'
    if field_type == 'calculated':
        try:
            field_eval.validate_formula(field_formula)
        except field_eval.FormulaError as exc:
            raise ValueError(f'{label} 公式无效：{exc}') from exc

    submitted_key = form.get(f'field_key_{idx}', '').strip()
    key = unique_key(
        field_key_from_label(
            submitted_key or label, f'field_{idx}'
        ),
        fields_so_far,
    )
    field = {
        'id': idx,
        'key': key,
        'label': label,
        'field_type': field_type,
        'required': bool(
            form.get(f'field_required_{idx}')
        ),
        'location': parse_field_location(
            form, idx, field_type
        ),
    }
    if field_type not in ('table', 'calculated'):
        field['default_value'] = limit_text(
            form.get(f'field_default_{idx}', '')
        )

    if field_type == 'select':
        options_text = form.get(f'field_options_{idx}', '')
        field['options'] = [
            limit_text(option.strip(), 200)
            for option in options_text.splitlines()
            if option.strip()
        ][:100]
    elif field_type == 'number':
        try:
            field['decimal_places'] = bounded_decimal_places(
                form.get(f'field_number_decimal_{idx}', 2)
            )
            min_raw = form.get(
                f'field_number_min_{idx}', ''
            ).strip()
            max_raw = form.get(
                f'field_number_max_{idx}', ''
            ).strip()
            field['min_value'] = (
                float(min_raw) if min_raw else None
            )
            field['max_value'] = (
                float(max_raw) if max_raw else None
            )
            if (
                field['min_value'] is not None
                and field['max_value'] is not None
                and field['min_value'] > field['max_value']
            ):
                raise ValueError(
                    f'{label} 的最小值不能大于最大值'
                )
            if field.get('default_value'):
                field['default_value'] = (
                    normalize_number_field_value(
                        field['default_value'], field
                    )
                )
        except ValueError as exc:
            message = str(exc)
            if message.startswith(f'{label} 的最小值'):
                raise
            raise ValueError(
                f'{label} 数字配置无效：{message}'
            ) from exc
    elif field_type == 'calculated':
        field['formula'] = field_formula
        field['decimal_places'] = bounded_decimal_places(
            form.get(f'field_decimal_{idx}', 2)
        )
        field['depends_on'] = list(
            field_eval.get_calc_deps(field)
        )
    elif field_type == 'table':
        field['columns'] = parse_table_columns(
            form, idx, label
        )
    return field


def parse_template_fields(form):
    fields = []
    for idx in range(MAX_TEMPLATE_FIELDS):
        if f'field_label_{idx}' not in form:
            break
        field = parse_single_field(form, idx, fields)
        if field:
            fields.append(field)
    if not fields:
        raise ValueError('请至少添加一个字段')
    for index, field in enumerate(fields):
        field['id'] = index
    return fields
