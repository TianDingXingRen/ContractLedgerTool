"""Focused regressions for form row limits and stable field identifiers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ledger_store
import template_def
from utils.production_forms import (
    MAX_ITEM_ROWS,
    contract_item_rows,
    production_notice_rows,
)
from utils.session_store import save_session_data


def _contract():
    return ledger_store.create_contract(
        {'title': '表单完整性测试合同'},
        {},
        '',
    )


def test_blank_existing_contract_item_is_rejected_before_line_number_changes(
    tmp_db,
):
    contract_id = _contract()
    item_id = ledger_store.save_contract_items(contract_id, [{
        'line_no': 1,
        'item_name': '产品一',
        'contracted_qty': 1,
    }])[0]

    with pytest.raises(ValueError, match='合同产品名称不能为空'):
        ledger_store.save_contract_items(contract_id, [{
            'id': item_id,
            'line_no': 1,
            'item_name': '',
            'contracted_qty': 1,
        }])

    assert ledger_store.get_contract_item(
        item_id, contract_id
    )['line_no'] == 1

    # Explicit deletion remains valid even when the submitted name is blank;
    # blank new padding rows remain no-ops.
    ledger_store.save_contract_items(contract_id, [{
        'id': item_id,
        'item_name': '',
        'delete': True,
    }])
    assert ledger_store.list_contract_items(contract_id) == []
    assert ledger_store.save_contract_items(
        contract_id, [{'item_name': '', 'line_no': 1}]
    ) == []


@pytest.mark.parametrize(
    ('parser', 'label'),
    (
        (contract_item_rows, '合同产品行数'),
        (production_notice_rows, '投产通知产品行数'),
    ),
)
def test_product_form_row_limits_are_explicit(parser, label):
    assert len(parser({'item_count': str(MAX_ITEM_ROWS)})) == MAX_ITEM_ROWS
    for invalid_count in ('-1', str(MAX_ITEM_ROWS + 1)):
        with pytest.raises(
            ValueError,
            match=rf'{label}必须在 0 到 {MAX_ITEM_ROWS} 之间',
        ):
            parser({'item_count': invalid_count})


def _set_template_session(client, paths, session_id, template_path):
    save_session_data(
        session_id,
        {
            'template_path': template_path,
            'template_filename': Path(template_path).name,
        },
        paths,
    )
    with client.session_transaction() as flask_session:
        flask_session['sid'] = session_id
        flask_session['_csrf_token'] = 'defaults-token'


def _post_defaults(client, values):
    return client.post(
        '/template-defaults',
        data={'csrf_token': 'defaults-token', **values},
    )


def _default_fields(text_id, table_id):
    columns = [{
        'key': 'name',
        'label': '名称',
        'field_type': 'text',
    }]
    return [
        {
            'id': text_id,
            'key': 'party',
            'label': '甲方',
            'field_type': 'text',
            'required': False,
            'default_value': '',
        },
        {
            'id': table_id,
            'key': 'items',
            'label': '明细',
            'field_type': 'table',
            'required': False,
            'columns': columns,
            'default_rows': [],
        },
    ]


def test_template_defaults_use_field_ids_and_fall_back_to_legacy_indexes(
    app,
    client,
    monkeypatch,
):
    paths = app.extensions['runtime_paths']
    monkeypatch.setattr(
        template_def,
        'TEMPLATES_DIR',
        str(paths.templates_dir),
    )

    current = template_def.TemplateDef.create(
        '按字段ID保存默认值',
        '',
        _default_fields(11, 42),
    )
    current_path = current.save()
    _set_template_session(client, paths, 'defaults-by-id', current_path)
    columns = current.data['fields'][1]['columns']
    response = _post_defaults(client, {
        'field_11': '按稳定 ID 保存',
        'field_42': json.dumps([{'name': '产品A'}], ensure_ascii=False),
        'table_cols_42': json.dumps(columns, ensure_ascii=False),
    })
    assert response.status_code == 200
    stored = template_def.TemplateDef.load(current_path).data['fields']
    assert stored[0]['default_value'] == '按稳定 ID 保存'
    assert stored[1]['default_rows'] == [{'name': '产品A'}]

    legacy = template_def.TemplateDef.create(
        '兼容旧下标默认值',
        '',
        _default_fields(51, 77),
    )
    legacy_path = legacy.save()
    _set_template_session(client, paths, 'defaults-by-index', legacy_path)
    legacy_columns = legacy.data['fields'][1]['columns']
    response = _post_defaults(client, {
        'field_0': '旧下标仍可读取',
        'field_1': json.dumps([{'name': '产品B'}], ensure_ascii=False),
        'table_cols_1': json.dumps(legacy_columns, ensure_ascii=False),
    })
    assert response.status_code == 200
    stored = template_def.TemplateDef.load(legacy_path).data['fields']
    assert stored[0]['default_value'] == '旧下标仍可读取'
    assert stored[1]['default_rows'] == [{'name': '产品B'}]


@pytest.mark.parametrize('existing_count', (99, 100))
def test_invoice_form_never_pads_past_allocation_limit(
    client,
    monkeypatch,
    existing_count,
):
    allocations = [{
        'contract_id': '',
        'production_notice_id': '',
        'payment_plan_id': '',
        'allocated_amount': '',
        'remark': '',
    } for _ in range(existing_count)]
    monkeypatch.setattr(
        ledger_store,
        'get_invoice',
        lambda _invoice_id: {'id': 1, 'allocations': allocations},
    )

    response = client.get('/invoices/1/edit')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="allocation_count" value="100"' in html
    assert html.count('data-allocation-row') == 100


def test_contract_item_frontend_enforces_required_name_and_row_limit():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates' / 'contract_items.html').read_text(
        encoding='utf-8'
    )
    script = (root / 'static' / 'js' / 'contract-items.js').read_text(
        encoding='utf-8'
    )

    assert (
        '{% if item and (item.id or item.item_name) %}'
        'required{% endif %}'
    ) in template
    assert 'const MAX_ITEM_ROWS = 500;' in script
    assert 'if (index >= MAX_ITEM_ROWS)' in script
    assert 'item_${index}_item_name" required' in script
