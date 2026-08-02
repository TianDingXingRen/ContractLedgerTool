from datetime import date

import ledger_store


def _create_contract():
    return ledger_store.create_contract(
        {
            'contract_no': 'GUI-130-001',
            'title': '桌面工作区验收合同',
            'counterparty': '华东精密制造有限公司',
            'amount': 1250000,
            'project_name': '高可靠组件采购',
        },
        {},
        '',
    )


def test_contract_workspace_tabs_default_and_invalid_fallback(client):
    contract_id = _create_contract()

    default_page = client.get(f'/contracts/{contract_id}')
    invalid_page = client.get(f'/contracts/{contract_id}?tab=not-a-tab')

    assert default_page.status_code == 200
    assert invalid_page.status_code == 200
    assert b'data-testid="contract-workspace"' in default_page.data
    assert '合同信息'.encode() in default_page.data
    assert '合同信息'.encode() in invalid_page.data
    assert b'data-testid="payment-plan-table"' not in default_page.data


def test_contract_workspace_payment_tab_and_safe_return(client):
    contract_id = _create_contract()
    ledger_store.insert_payment_plans(contract_id, [{
        'phase_name': '到货验收款',
        'payment_type': 'conditional',
        'due_date': '2026-08-10',
        'due_amount': 320000,
        'paid_amount': 80000,
        'paid_date': '2026-07-18',
        'confirm_status': 'confirmed',
        'payment_status': 'partial',
        'parse_status': 'manual',
    }])

    response = client.get(f'/contracts/{contract_id}?tab=payments')

    assert response.status_code == 200
    assert b'data-testid="payment-plan-table"' in response.data
    assert '到货验收款'.encode() in response.data
    assert '登记付款'.encode() in response.data
    assert b'<colgroup>' not in response.data


def test_contract_workspace_summary_uses_confirmed_effective_amounts(app):
    contract_id = _create_contract()
    ledger_store.insert_payment_plans(contract_id, [
        {
            'phase_name': '已确认计划', 'payment_type': 'fixed_date',
            'due_date': '2026-07-01', 'due_amount': 500000,
            'paid_amount': 120000, 'paid_date': '2026-07-12',
            'confirm_status': 'confirmed',
            'payment_status': 'partial', 'parse_status': 'manual',
        },
        {
            'phase_name': '待确认计划', 'payment_type': 'fixed_date',
            'due_date': '2026-07-01', 'due_amount': 200000,
            'paid_amount': 0, 'confirm_status': 'pending',
            'payment_status': 'unpaid', 'parse_status': 'manual',
        },
    ])

    summary = ledger_store.get_contract_workspace_summary(
        contract_id, today=date(2026, 7, 22)
    )

    assert summary['confirmed_plan_count'] == 1
    assert summary['payment_due'] == 500000
    assert summary['payment_paid'] == 120000
    assert summary['payment_unpaid'] == 380000
    assert summary['overdue_count'] == 1
