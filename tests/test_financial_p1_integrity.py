import pytest

import ledger_store
from core.domain_errors import ConflictError


def _contract(number, *, status='active'):
    return ledger_store.create_contract(
        {
            'contract_no': number,
            'title': f'{number} 测试合同',
            'amount': 1000,
            'status': status,
        },
        {},
        '',
    )


def _invoice(number, **overrides):
    return {
        'invoice_no': number,
        'amount_ex_tax': 100,
        'tax_amount': 13,
        'total_amount': 113,
        **overrides,
    }


def _invoice_form(number, revision):
    return {
        'invoice_no': number,
        'currency': 'CNY',
        'amount_ex_tax': '100',
        'tax_amount': '13',
        'total_amount': '113',
        'invoice_status': 'valid',
        'review_status': 'pending',
        'deduction_status': 'not_applicable',
        'allocation_count': '0',
        'revision': str(revision),
    }


def test_payment_plan_execution_trace_blocks_all_hard_delete_paths(tmp_db):
    contract_id = _contract('PAY-KEEP-001')
    removable_id = ledger_store.insert_payment_plan(
        contract_id, {'phase_name': '可删除节点', 'due_amount': 100}
    )
    paid_id = ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '已付款节点',
            'due_amount': 100,
            'paid_amount': 20,
            'paid_date': '2026-08-11',
            'confirm_status': 'confirmed',
        },
    )

    with pytest.raises(ValueError, match='执行记录.*不能删除'):
        ledger_store.save_payment_plan_changes(
            contract_id,
            [
                {'id': removable_id, 'delete': True},
                {'id': paid_id, 'delete': True},
            ],
        )

    # The rejected batch is atomic: the otherwise removable row is restored too.
    with ledger_store.get_conn() as conn:
        remaining = {
            row[0]
            for row in conn.execute(
                'SELECT id FROM payment_plans WHERE contract_id = ?',
                (contract_id,),
            ).fetchall()
        }
    assert remaining == {removable_id, paid_id}

    with pytest.raises(ValueError, match='执行记录.*不能删除'):
        ledger_store.delete_payment_plan(paid_id, contract_id)
    assert ledger_store.delete_payment_plan(removable_id, contract_id) == 1

    ledger_store.soft_delete_contract(contract_id)
    with pytest.raises(ValueError, match='付款或业务执行记录.*不能永久删除'):
        ledger_store.permanently_delete_contract(contract_id)
    with ledger_store.get_conn() as conn:
        assert conn.execute(
            'SELECT 1 FROM contracts WHERE id = ?', (contract_id,)
        ).fetchone()
        assert conn.execute(
            'SELECT 1 FROM payment_plans WHERE id = ?', (paid_id,)
        ).fetchone()


def test_paid_payment_plan_delete_control_is_disabled(client):
    contract_id = _contract('PAY-KEEP-UI')
    ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '已执行付款',
            'due_amount': 100,
            'paid_amount': 100,
            'paid_date': '2026-08-11',
            'confirm_status': 'confirmed',
        },
    )

    response = client.get(f'/contracts/{contract_id}?tab=payments')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '保留记录' in html
    assert '已有付款或业务执行记录，必须保留审计记录' in html

    ledger_store.soft_delete_contract(contract_id)
    deleted_detail = client.get(f'/contracts/{contract_id}')
    assert deleted_detail.status_code == 200
    deleted_html = deleted_detail.get_data(as_text=True)
    assert '付款执行记录需保留，不能永久删除' in deleted_html
    assert f'/contracts/{contract_id}/permanent-delete' not in deleted_html


def test_void_contract_cannot_receive_invoice_allocation(tmp_db):
    contract_id = _contract('VOID-INVOICE-001', status='void')

    with pytest.raises(ValueError, match='已作废合同不能新增或修改发票分摊'):
        ledger_store.save_invoice(
            _invoice('VOID-ALLOC-001'),
            [{'contract_id': contract_id, 'allocated_amount': 113}],
        )

    assert ledger_store.list_invoices() == []

    invoice_id = ledger_store.save_invoice(_invoice('VOID-ALLOC-EDIT'), [])
    revision = ledger_store.get_invoice(invoice_id)['revision']
    with pytest.raises(ValueError, match='已作废合同不能新增或修改发票分摊'):
        ledger_store.save_invoice(
            _invoice('VOID-ALLOC-EDIT'),
            [{'contract_id': contract_id, 'allocated_amount': 113}],
            invoice_id=invoice_id,
            expected_revision=revision,
        )
    current = ledger_store.get_invoice(invoice_id)
    assert current['revision'] == revision
    assert current['allocations'] == []


def test_void_contract_invoice_targets_api_is_conflict(client):
    contract_id = _contract('VOID-INVOICE-API', status='void')

    response = client.get(f'/api/contracts/{contract_id}/invoice-targets')

    assert response.status_code == 409
    assert response.get_json()['error'] == '已作废合同不能新增或修改发票分摊'
    form_html = client.get('/invoices/new').get_data(as_text=True)
    assert 'VOID-INVOICE-API' in form_html
    assert '（已作废，不可分摊）' in form_html
    detail_html = client.get(
        f'/contracts/{contract_id}?tab=invoices'
    ).get_data(as_text=True)
    assert '已作废合同不能登记发票分摊' in detail_html


def test_invoice_revision_cas_preserves_winning_edit_and_allocations(tmp_db):
    contract_id = _contract('INV-CAS-001')
    invoice_id = ledger_store.save_invoice(
        _invoice('INV-CAS-001'),
        [{'contract_id': contract_id, 'allocated_amount': 100}],
    )
    baseline = ledger_store.get_invoice(invoice_id)
    assert baseline['revision'] == 1

    ledger_store.save_invoice(
        _invoice('INV-CAS-001', remark='先提交的修改'),
        [{'contract_id': contract_id, 'allocated_amount': 90}],
        invoice_id=invoice_id,
        expected_revision=baseline['revision'],
    )

    with pytest.raises(ConflictError, match='已被其他页面修改'):
        ledger_store.save_invoice(
            _invoice('INV-CAS-001', remark='陈旧页面覆盖'),
            [{'contract_id': contract_id, 'allocated_amount': 10}],
            invoice_id=invoice_id,
            expected_revision=baseline['revision'],
        )

    current = ledger_store.get_invoice(invoice_id)
    assert current['revision'] == 2
    assert current['remark'] == '先提交的修改'
    assert current['allocations'][0]['allocated_amount'] == 90
    assert [row['action'] for row in current['history']].count('edit') == 1


def test_invoice_store_edit_requires_revision_baseline(tmp_db):
    invoice_id = ledger_store.save_invoice(_invoice('INV-NO-REVISION'), [])

    with pytest.raises(ValueError, match='必须提供版本'):
        ledger_store.save_invoice(
            _invoice('INV-NO-REVISION', remark='不允许无条件覆盖'),
            [],
            invoice_id=invoice_id,
        )

    current = ledger_store.get_invoice(invoice_id)
    assert current['remark'] == ''
    assert current['revision'] == 1


def test_invoice_edit_route_returns_409_and_preserves_stale_submission(client):
    invoice_id = ledger_store.save_invoice(_invoice('INV-ROUTE-BASE'), [])
    baseline = ledger_store.get_invoice(invoice_id)
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'invoice-cas-token'

    winner = client.post(
        f'/invoices/{invoice_id}/edit',
        data={
            **_invoice_form('INV-ROUTE-WINNER', baseline['revision']),
            'csrf_token': 'invoice-cas-token',
        },
    )
    stale = client.post(
        f'/invoices/{invoice_id}/edit',
        data={
            **_invoice_form('INV-ROUTE-STALE', baseline['revision']),
            'csrf_token': 'invoice-cas-token',
        },
    )

    assert winner.status_code == 302
    assert stale.status_code == 409
    html = stale.get_data(as_text=True)
    assert '发票已被其他页面修改' in html
    assert 'value="INV-ROUTE-STALE"' in html
    current = ledger_store.get_invoice(invoice_id)
    assert current['invoice_no'] == 'INV-ROUTE-WINNER'
    assert current['revision'] == baseline['revision'] + 1


def test_invoice_edit_route_requires_revision(client):
    invoice_id = ledger_store.save_invoice(_invoice('INV-ROUTE-REV'), [])
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'invoice-revision-token'
    form = _invoice_form('INV-ROUTE-REV', 1)
    form.pop('revision')
    form['csrf_token'] = 'invoice-revision-token'

    response = client.post(f'/invoices/{invoice_id}/edit', data=form)

    assert response.status_code == 400
    assert '缺少发票版本' in response.get_data(as_text=True)
    assert ledger_store.get_invoice(invoice_id)['revision'] == 1
