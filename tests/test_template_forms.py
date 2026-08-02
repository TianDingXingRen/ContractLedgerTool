"""Unit tests for framework-neutral template form parsing."""

import pytest

from utils.template_forms import parse_template_fields


def test_parse_template_fields_preserves_table_column_semantics():
    fields = parse_template_fields(
        {
            'field_label_0': '明细',
            'field_key_0': 'items',
            'field_type_0': 'table',
            'field_table_index_0': '2',
            'field_template_row_index_0': '1',
            'col_label_0_0': '数量',
            'col_type_0_0': 'number',
            'col_decimal_0_0': '3',
            'col_default_0_0': '1.250',
            'col_label_0_1': '小计',
            'col_type_0_1': 'calculated',
            'col_formula_0_1': 'qty * 2',
        }
    )

    table = fields[0]
    assert table['location'] == {
        'type': 'table',
        'table_index': 2,
        'template_row_index': 1,
    }
    assert table['columns'][0]['field_type'] == 'number'
    assert table['columns'][0]['decimal_places'] == 3
    assert table['columns'][0]['default_value'] == '1.250'
    assert table['columns'][1]['field_type'] == 'calculated'
    assert table['columns'][1]['default_value'] == ''


def test_parse_template_fields_rejects_empty_definition():
    with pytest.raises(ValueError, match='请至少添加一个字段'):
        parse_template_fields({})


def test_parse_template_fields_preserves_number_bounds_error():
    form = {
        'field_label_0': '金额',
        'field_type_0': 'number',
        'field_number_min_0': '10',
        'field_number_max_0': '1',
    }

    with pytest.raises(
        ValueError,
        match='金额 的最小值不能大于最大值',
    ):
        parse_template_fields(form)


def test_parse_template_fields_rejects_invalid_formula():
    form = {
        'field_label_0': '合计',
        'field_type_0': 'calculated',
        'field_formula_0': '__import__("os")',
    }

    with pytest.raises(ValueError, match='合计 公式无效'):
        parse_template_fields(form)
