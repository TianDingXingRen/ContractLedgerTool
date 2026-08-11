"""High-risk workflow coverage for slim payment and production routes."""

from __future__ import annotations

import json

import pytest

import ledger_store
from utils.payment_forms import (
    contract_serial_entries,
    normalized_form_date,
    parse_plan_ids,
    payment_plan_changes,
    payment_rule_event,
    payment_rule_values,
)
from utils.production_forms import (
    contract_item_rows,
    production_notice_header,
    production_notice_rows,
)
from utils.security import MAX_PLAN_ROWS


def _csrf(client, token):
    with client.session_transaction() as session:
        session['_csrf_token'] = token
    return token


def _post(client, path, token, data=None):
    payload = {'csrf_token': token}
    payload.update(data or {})
    return client.post(path, data=payload, follow_redirects=False)


def test_payment_routes_cover_contract_rules_plans_and_batches(client):
    token = _csrf(client, 'payment-slimming-token')
    contract_id = ledger_store.create_contract(
        {
            'contract_no': 'PAY-SLIM-001',
            'title': '付款路由瘦身测试',
            'project_name': '付款测试项目',
            'coverage_start': 1,
            'coverage_end': 2,
        },
        {},
        'payment-slimming.docx',
    )

    assert _post(
        client, f'/contracts/{contract_id}/serials/sync', token
    ).status_code == 302
    serials = ledger_store.list_contract_serials(contract_id)
    serial_form = {'serial_count': str(len(serials))}
    for index, serial in enumerate(serials):
        serial_form.update(
            {
                f'serial_{index}_id': str(serial['id']),
                f'serial_{index}_amount': str(
                    1000 * (index + 1)
                ),
                f'serial_{index}_remark': f'编号{index + 1}',
            }
        )
    assert _post(
        client,
        f'/contracts/{contract_id}/serials/save',
        token,
        serial_form,
    ).status_code == 302
    assert _post(
        client,
        f'/contracts/{contract_id}/serials/bulk-amount',
        token,
        {'bulk_amount': '3000', 'replace_existing': '1'},
    ).status_code == 302

    mapping = ledger_store.insert_payment_rules(
        contract_id,
        [
            {
                'phase_name': '验收付款',
                'scope': 'contract',
                'trigger_event_type': 'other',
                'trigger_event': '验收完成',
                'amount_basis': 'contract_total',
                'ratio': 10,
                'repeat_mode': 'once',
                'parse_status': 'exact',
                'confirm_status': 'pending',
                'rule_fingerprint': 'payment-slimming-rule',
            }
        ],
    )
    rule_id = mapping['payment-slimming-rule']
    assert _post(
        client,
        f'/contracts/{contract_id}/payment-rules/{rule_id}/status',
        token,
        {'status': 'confirmed'},
    ).status_code == 302
    assert _post(
        client,
        f'/contracts/{contract_id}/payment-rules/{rule_id}/edit',
        token,
        {
            'phase_name': '验收付款（修订）',
            'scope': 'contract',
            'trigger_event_type': 'other',
            'trigger_event': '最终验收完成',
            'trigger_days': '5',
            'amount_basis': 'contract_total',
            'amount_basis_text': '合同总额',
            'ratio': '15',
            'repeat_mode': 'once',
        },
    ).status_code == 302
    assert _post(
        client,
        f'/contracts/{contract_id}/payment-rules/{rule_id}/trigger',
        token,
        {
            'reference_no': 'ACCEPT-001',
            'event_date': '2026-08-01',
            'reference_name': '最终验收',
            'base_amount': '10000',
        },
    ).status_code == 302

    assert _post(
        client,
        f'/contracts/{contract_id}/payments/save',
        token,
        {
            'plan_count': '1',
            'plan_0_phase_name': '人工付款计划',
            'plan_0_due_date': '2026-08-10',
            'plan_0_due_amount': '800',
            'plan_0_confirm_status': 'pending',
        },
    ).status_code == 302
    assert _post(
        client,
        f'/contracts/{contract_id}/payments/confirm-all',
        token,
    ).status_code == 302

    plan = next(
        row
        for row in ledger_store.list_payment_plans(
            contract_id=contract_id
        )
        if row['phase_name'] == '人工付款计划'
    )
    encoded_ids = json.dumps([plan['id']])
    assert _post(
        client,
        '/payment-plans/batch-confirm',
        token,
        {'ids': encoded_ids, 'view': 'work'},
    ).status_code == 302
    assert _post(
        client,
        '/payment-plans/batch-paid',
        token,
        {
            'ids': encoded_ids,
            'paid_date': '2026-08-11',
            'view': 'work',
        },
    ).status_code == 302
    assert _post(
        client,
        f'/payment-plans/{plan["id"]}/quick-update',
        token,
        {'action': 'unpaid', 'view': 'work'},
    ).status_code == 302
    assert ledger_store.get_payment_plan(plan['id'])['paid_amount'] == 0


def _notice_form(item_id, number, start, *, quantity=1):
    end = start + quantity - 1
    return {
        'notice_no': number,
        'notice_date': '2026-08-02',
        'supplier_name': '测试供应商',
        'project_name': '路由瘦身项目',
        'operator': '测试员',
        'item_count': '1',
        'item_0_contract_item_id': str(item_id),
        'item_0_notice_qty': str(quantity),
        'item_0_serial_start': str(start),
        'item_0_serial_end': str(end),
        'item_0_required_delivery_date': '2026-09-01',
    }


def test_production_routes_cover_drafts_and_state_transitions(client):
    token = _csrf(client, 'production-slimming-token')
    contract_id = ledger_store.create_contract(
        {
            'contract_no': 'PROD-SLIM-001',
            'title': '生产路由瘦身测试',
            'counterparty': '测试供应商',
            'amount': 10_000,
        },
        {},
        'production-slimming.docx',
    )
    response = _post(
        client,
        f'/contracts/{contract_id}/items',
        token,
        {
            'operator': '测试员',
            'item_count': '1',
            'item_0_line_no': '1',
            'item_0_item_name': '路由测试产品',
            'item_0_contracted_qty': '5',
            'item_0_unit': '个',
            'item_0_unit_price': '100',
            'item_0_serial_start': '1',
            'item_0_serial_end': '5',
        },
    )
    assert response.status_code == 302
    item_id = ledger_store.list_contract_items(contract_id)[0]['id']

    response = _post(
        client,
        f'/contracts/{contract_id}/production-notices/new',
        token,
        _notice_form(item_id, 'PROD-ROUTE-A', 1),
    )
    assert response.status_code == 302
    notice_a = ledger_store.list_production_notices(
        contract_id=contract_id
    )[0]['id']

    edited = _notice_form(item_id, 'PROD-ROUTE-A', 1)
    edited['remark'] = '草稿已编辑'
    assert _post(
        client,
        f'/production-notices/{notice_a}/edit',
        token,
        edited,
    ).status_code == 302
    for action in ('issue', 'acknowledge', 'close'):
        assert _post(
            client,
            f'/production-notices/{notice_a}/{action}',
            token,
            {'operator': '测试员'},
        ).status_code == 302
    assert (
        ledger_store.get_production_notice(notice_a)['status']
        == 'closed'
    )

    notice_b = ledger_store.create_production_notice(
        contract_id,
        {
            'notice_no': 'PROD-ROUTE-B',
            'notice_date': '2026-08-02',
        },
        [
            {
                'contract_item_id': item_id,
                'notice_qty': '1',
                'serial_start': '2',
                'serial_end': '2',
            }
        ],
    )
    assert _post(
        client,
        f'/production-notices/{notice_b}/issue',
        token,
        {'operator': '测试员'},
    ).status_code == 302
    revision = _post(
        client,
        f'/production-notices/{notice_b}/revise',
        token,
        {'operator': '测试员'},
    )
    assert revision.status_code == 302
    assert '/edit' in revision.headers['Location']

    notice_c = ledger_store.create_production_notice(
        contract_id,
        {
            'notice_no': 'PROD-ROUTE-C',
            'notice_date': '2026-08-02',
        },
        [
            {
                'contract_item_id': item_id,
                'notice_qty': '1',
                'serial_start': '3',
                'serial_end': '3',
            }
        ],
    )
    assert _post(
        client,
        f'/production-notices/{notice_c}/cancel',
        token,
        {'operator': '测试员', 'reason': '测试取消'},
    ).status_code == 302
    assert (
        ledger_store.get_production_notice(notice_c)['status']
        == 'cancelled'
    )


def test_route_form_parsers_cover_valid_and_invalid_boundaries():
    assert parse_plan_ids('[2, 1, 2]') == [2, 1]
    with pytest.raises(ValueError, match='ID 列表'):
        parse_plan_ids('{invalid')
    with pytest.raises(ValueError, match='单次不能超过'):
        parse_plan_ids(json.dumps(list(range(MAX_PLAN_ROWS + 1))))
    assert normalized_form_date(
        {'paid_date': '2026/08/03'}, 'paid_date'
    ) == '2026-08-03'
    with pytest.raises(ValueError, match='日期格式'):
        normalized_form_date({'paid_date': 'not-a-date'}, 'paid_date')

    assert contract_serial_entries(
        {
            'serial_count': '1',
            'serial_0_id': '7',
            'serial_0_amount': '100',
            'serial_0_remark': '测试',
        },
        2,
    )[0]['id'] == '7'
    with pytest.raises(ValueError, match='数量无效'):
        contract_serial_entries({'serial_count': 'x'}, 2)
    with pytest.raises(ValueError, match='不能超过'):
        contract_serial_entries({'serial_count': '3'}, 2)

    rule = payment_rule_values(
        {
            'trigger_days': '5',
            'ratio': '10.5',
            'explicit_amount': '100',
        }
    )
    assert rule['trigger_days'] == 5
    assert rule['ratio'] == 10.5
    with pytest.raises(ValueError, match='后置天数必须是整数'):
        payment_rule_values({'trigger_days': '1.5'})
    with pytest.raises(ValueError, match='有效数字'):
        payment_rule_values({'ratio': 'bad'})

    event = payment_rule_event(
        {'reference_no': 'E-1', 'event_date': '2026-08-03'}
    )
    assert event['event_date'] == '2026-08-03'
    with pytest.raises(ValueError, match='业务事件日期'):
        payment_rule_event({'event_date': 'bad'})

    changes = payment_plan_changes(
        {
            'plan_count': '2',
            'plan_0_id': '9',
            'plan_0_delete': '1',
            'plan_1_phase_name': '新增节点',
            'plan_1_due_amount': '100',
        }
    )
    assert changes[0] == {'id': 9, 'delete': True}
    assert changes[1]['data']['phase_name'] == '新增节点'
    with pytest.raises(ValueError, match='行数无效'):
        payment_plan_changes({'plan_count': 'bad'})
    with pytest.raises(ValueError, match='ID 无效'):
        payment_plan_changes(
            {
                'plan_count': '1',
                'plan_0_id': 'bad',
                'plan_0_delete': '1',
            }
        )

    items = contract_item_rows(
        {
            'item_count': '1',
            'item_0_item_name': '产品',
            'item_0_contracted_qty': '2',
        }
    )
    assert items[0]['item_name'] == '产品'
    with pytest.raises(ValueError, match='合同产品行数'):
        contract_item_rows({'item_count': 'bad'})

    rows = production_notice_rows(
        {
            'item_count': '1',
            'item_0_contract_item_id': '1',
            'item_0_notice_qty': '1',
            'item_0_required_delivery_date': '2026/09/01',
        }
    )
    assert rows[0]['required_delivery_date'] == '2026-09-01'
    with pytest.raises(ValueError, match='要求交付日期'):
        production_notice_rows(
            {
                'item_count': '1',
                'item_0_required_delivery_date': 'bad',
            }
        )
    assert production_notice_header(
        {'notice_date': '2026/08/03'}
    )['notice_date'] == '2026-08-03'
