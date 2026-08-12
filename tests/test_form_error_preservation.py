"""Regressions for failed form submissions retaining user input."""

from __future__ import annotations

import pytest

import ledger_store
from services import procurement_project_service


def _csrf(client, token='form-preservation-token'):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = token
    return token


def _contract():
    return ledger_store.create_contract(
        {
            'contract_no': 'FORM-PRESERVE-001',
            'title': '表单回显测试合同',
        },
        {},
        '',
    )


def test_contract_item_validation_error_retains_every_posted_value(client):
    token = _csrf(client)
    contract_id = _contract()

    response = client.post(
        f'/contracts/{contract_id}/items',
        data={
            'csrf_token': token,
            'operator': '保留操作人',
            'item_count': '2',
            'item_0_line_no': '7',
            'item_0_item_name': '必须保留的产品甲',
            'item_0_spec_model': 'SPEC-KEEP-A',
            'item_0_contracted_qty': '不是数量',
            'item_0_unit': '套',
            'item_1_line_no': '8',
            'item_1_item_name': '必须保留的产品乙',
            'item_1_drawing_no': 'DRAW-KEEP-B',
            'item_1_contracted_qty': '2',
            'item_1_unit': '件',
        },
    )

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    for value in (
        '保留操作人',
        '必须保留的产品甲',
        'SPEC-KEEP-A',
        '不是数量',
        '必须保留的产品乙',
        'DRAW-KEEP-B',
    ):
        assert value in html
    assert ledger_store.list_contract_items(contract_id) == []


@pytest.mark.parametrize('invalid_count', ['invalid', '-1', '501'])
def test_contract_item_invalid_row_count_retains_posted_values(
    client, invalid_count
):
    token = _csrf(client)
    contract_id = _contract()

    response = client.post(
        f'/contracts/{contract_id}/items',
        data={
            'csrf_token': token,
            'operator': '解析失败也保留',
            'item_count': invalid_count,
            'item_0_line_no': '17',
            'item_0_item_name': '解析前输入不得丢失',
            'item_0_contracted_qty': '7',
        },
    )

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert '解析失败也保留' in html
    assert '解析前输入不得丢失' in html
    assert 'value="17"' in html


def test_contract_item_repository_rejects_duplicate_ids_without_history(
    tmp_db,
):
    contract_id = _contract()
    item_id = ledger_store.save_contract_items(contract_id, [{
        'line_no': 1,
        'item_name': '原产品',
        'contracted_qty': 3,
    }])[0]
    history_before = ledger_store.list_contract_item_history(contract_id)

    with pytest.raises(ValueError, match='ID 不能重复提交'):
        ledger_store.save_contract_items(contract_id, [
            {
                'id': item_id,
                'line_no': 1,
                'item_name': '第一次更新',
                'contracted_qty': 3,
            },
            {
                'id': item_id,
                'line_no': 2,
                'item_name': '第二次更新',
                'contracted_qty': 3,
            },
        ])

    assert ledger_store.get_contract_item(
        item_id, contract_id
    )['item_name'] == '原产品'
    assert (
        ledger_store.list_contract_item_history(contract_id)
        == history_before
    )


def test_new_procurement_number_conflict_retains_every_posted_value(client):
    token = _csrf(client)
    procurement_project_service.create_project({
        'project_no': 'CG-FORM-DUPLICATE',
        'project_name': '已存在项目',
    })
    submitted = {
        'csrf_token': token,
        'project_no': 'CG-FORM-DUPLICATE',
        'project_name': '冲突时保留的项目名',
        'purchase_method': 'single_source',
        'demand_department': '保留需求部门',
        'owner': '保留经办人',
        'delivery_place': '保留交付地点',
        'budget_amount': '12345.67',
        'target_price': '12000.50',
        'delivery_requirement': '保留交付要求',
        'payment_requirement': '保留付款要求',
        'remark': '保留备注',
    }

    response = client.post('/procurement/projects/new', data=submitted)

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert '项目编号已存在' in html
    for value in submitted.values():
        assert value in html
