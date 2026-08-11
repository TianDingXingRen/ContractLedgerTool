from datetime import date

import ledger_store
from services import payment_queries
from utils.payment_forms import payment_filter_args


def _create_contract(contract_no, title, project_name):
    return ledger_store.create_contract(
        {
            'contract_no': contract_no,
            'title': title,
            'project_name': project_name,
            'coverage_start': 1,
            'coverage_end': 2,
        },
        {},
        '',
    )


def _set_csrf(client, token='payment-contract-filter-token'):
    with client.session_transaction() as session:
        session['_csrf_token'] = token
    return token


def test_payment_filter_args_accepts_only_positive_contract_ids():
    assert payment_filter_args({'contract_id': ' 17 '})['contract_id'] == 17
    for invalid in ('', '0', '-3', '1.5', 'invalid', str(1 << 63)):
        assert payment_filter_args({'contract_id': invalid})['contract_id'] == ''


def test_contract_filter_keeps_rows_summary_options_and_navigation_in_sync(
    app, client
):
    first_id = _create_contract('FILTER-001', '筛选合同甲', '项目甲')
    second_id = _create_contract('FILTER-002', '筛选合同乙', '项目乙')
    no_plan_id = _create_contract('FILTER-003', '无付款计划合同', '项目丙')

    later_id = ledger_store.insert_payment_plan(first_id, {
        'phase_name': '甲合同后到期',
        'due_date': '2030-06-10',
        'due_amount': 200,
        'confirm_status': 'confirmed',
    })
    earlier_id = ledger_store.insert_payment_plan(first_id, {
        'phase_name': '甲合同先到期',
        'due_date': '2030-05-10',
        'due_amount': 100,
        'confirm_status': 'pending',
    })
    second_plan_id = ledger_store.insert_payment_plan(second_id, {
        'phase_name': '乙合同付款计划',
        'due_date': '2030-04-10',
        'due_amount': 300,
        'confirm_status': 'confirmed',
    })

    context = payment_queries.payment_plan_page(
        {'contract_id': first_id}, 1, date(2030, 1, 1)
    )
    assert [row['id'] for row in context['plans']] == [earlier_id, later_id]
    assert context['payment_summary']['count'] == 2
    assert {row['id'] for row in context['payment_contract_options']} == {
        first_id,
        second_id,
    }
    assert no_plan_id not in {
        row['id'] for row in context['payment_contract_options']
    }
    assert [
        row['id'] for row in ledger_store.list_payment_plans()
    ] == [second_plan_id, earlier_id, later_id]

    combined = payment_queries.payment_plan_page(
        {'contract_id': first_id, 'project_name': '项目乙'},
        1,
        date(2030, 1, 1),
    )
    assert combined['plans'] == []
    assert combined['payment_summary']['count'] == 0

    filtered = client.get(
        f'/payment-plans?view=detail&contract_id={first_id}'
    )
    html = filtered.get_data(as_text=True)
    assert filtered.status_code == 200
    assert '甲合同先到期' in html
    assert '甲合同后到期' in html
    assert '乙合同付款计划' not in html
    assert f'<option value="{first_id}" selected>' in html
    assert f'contract_id={first_id}' in html

    missing = payment_queries.payment_plan_page(
        {'contract_id': 999999}, 1, date(2030, 1, 1)
    )
    assert missing['plans'] == []
    assert missing['payment_summary']['count'] == 0

    ignored = client.get('/payment-plans?contract_id=not-an-integer')
    ignored_html = ignored.get_data(as_text=True)
    assert '甲合同先到期' in ignored_html
    assert '乙合同付款计划' in ignored_html

    response = client.post(
        f'/payment-plans/{earlier_id}/quick-update',
        data={
            'csrf_token': _set_csrf(client),
            'action': 'confirm',
            'view': 'detail',
            'contract_id': str(first_id),
            'page': '1',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f'contract_id={first_id}' in response.headers['Location']


def test_not_applicable_contract_is_exposed_by_payment_read_models(app, client):
    contract_id = ledger_store.create_contract(
        {
            'contract_no': 'FILTER-NA',
            'title': '不适用发次合同',
            'coverage_not_applicable': True,
        },
        {},
        '',
    )
    # Keep the read-model test independent of the contract creation adapter.
    with ledger_store.get_conn() as conn:
        conn.execute(
            """UPDATE contracts
                  SET coverage_not_applicable = 1,
                      coverage_start = NULL,
                      coverage_end = NULL
                WHERE id = ?""",
            (contract_id,),
        )
    plan_id = ledger_store.insert_payment_plan(contract_id, {
        'phase_name': '不适用合同验收款',
        'due_date': date.today().strftime('%Y-%m-%d'),
        'due_amount': 68000,
        'confirm_status': 'confirmed',
    })

    row = ledger_store.list_payment_plans(contract_id=contract_id)[0]
    assert row['coverage_not_applicable'] == 1
    assert row['serial_no'] is None
    today_text = date.today().strftime('%Y-%m-%d')
    exported_row = ledger_store.next_month_payment_plans(
        today_text, today_text
    )[0]
    assert exported_row['coverage_not_applicable'] == 1

    page = client.get(f'/payment-plans?contract_id={contract_id}')
    html = page.get_data(as_text=True)
    assert 'FILTER-NA · 不适用' in html

    payload = client.get('/api/payments/due-soon?days=1').get_json()
    payment = next(item for item in payload['payments'] if item['id'] == plan_id)
    assert payment['coverage_not_applicable'] is True

    historical_id = ledger_store.create_contract({
        'contract_no': 'FILTER-NA-HISTORY',
        'title': '保留历史发次合同',
    }, {}, '')
    with ledger_store.get_conn() as conn:
        serial_id = conn.execute(
            """
            INSERT INTO contract_serials
                (contract_id, serial_no, status, created_at, updated_at)
            VALUES (?, 9, 'active', ?, ?)
            """,
            (historical_id, '2026-01-01', '2026-01-01'),
        ).lastrowid
    ledger_store.insert_payment_plan(historical_id, {
        'contract_serial_id': serial_id,
        'phase_name': '历史发次节点',
    })
    ledger_store.update_contract(historical_id, {
        'coverage_not_applicable': 1,
        'coverage_start': None,
        'coverage_end': None,
    })
    history_html = client.get(
        f'/payment-plans?contract_id={historical_id}'
    ).get_data(as_text=True)
    assert '第 9 发（历史关联 · 合同发次不适用）' in history_html
