import io
import sqlite3

import pytest

import ledger_store
from ledger_store.contract_items import parse_contracted_qty
from routes.invoices_bp import _resolved_invoice_file


def _contract():
    return ledger_store.create_contract(
        {
            'contract_no': 'PN-TEST-001',
            'title': '投产通知测试合同',
            'counterparty': '测试供应商',
            'amount': 1000,
            'project_name': '测试项目',
        },
        {},
        '',
    )


def _baseline(contract_id, qty=10, unit_price=100):
    item_id = ledger_store.save_contract_items(contract_id, [{
        'line_no': 1,
        'item_name': '测试产品',
        'spec_model': 'A-01',
        'contracted_qty': qty,
        'unit': '个',
        'unit_price': unit_price,
    }])[0]
    with ledger_store.get_conn() as conn:
        conn.execute(
            'UPDATE contract_items SET serial_start = 1, serial_end = ? WHERE id = ?',
            (qty, item_id),
        )
    return item_id


def _rule(contract_id):
    mapping = ledger_store.insert_payment_rules(contract_id, [{
        'phase_name': '每次投产付款',
        'rule_type': 'recurring',
        'scope': 'production_notice',
        'trigger_event_type': 'production_notice_issued',
        'trigger_event': '每次投产通知发出',
        'amount_basis': 'production_notice_total',
        'ratio': 30,
        'repeat_mode': 'each_event',
        'parse_status': 'exact',
        'confirm_status': 'confirmed',
        'rule_fingerprint': 'production-notice-test-rule',
    }])
    return mapping['production-notice-test-rule']


def _notice(contract_id, item_id, qty, start, end, number):
    return ledger_store.create_production_notice(
        contract_id,
        {
            'notice_no': number,
            'notice_date': '2026-07-22',
            'operator': '测试员',
        },
        [{
            'contract_item_id': item_id,
            'notice_qty': str(qty),
            'serial_start': str(start),
            'serial_end': str(end),
        }],
    )


def test_contract_quantity_parser_is_linear_and_preserves_supported_formats():
    assert parse_contracted_qty(' 12.00 件 ') == 12
    assert parse_contracted_qty('１２套') == 12
    for invalid in ('0', '1.20', '12.0.0', '0' + (' ' * 20_000) + '件'):
        with pytest.raises(ValueError, match='不是正整数'):
            parse_contracted_qty(invalid)


def test_invoice_storage_rejects_paths_outside_runtime_root(client):
    with client.application.app_context():
        with pytest.raises(ValueError, match='路径无效'):
            _resolved_invoice_file('../outside.pdf')
        with pytest.raises(ValueError, match='路径无效'):
            _resolved_invoice_file(r'..\outside.pdf')


def test_invoice_upload_removes_file_when_database_registration_fails(
    app, client, monkeypatch,
):
    invoice_id = ledger_store.save_invoice(
        {
            'invoice_code': '044001',
            'invoice_no': 'UPLOAD-ROLLBACK',
            'seller_tax_no': 'TAX-UPLOAD',
            'amount_ex_tax': 100,
            'tax_amount': 13,
            'total_amount': 113,
        },
        [],
    )
    monkeypatch.setattr(
        ledger_store,
        'add_invoice_file',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError('database registration failed')
        ),
    )
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'invoice-upload-token'

    response = client.post(
        f'/invoices/{invoice_id}/files',
        data={
            'csrf_token': 'invoice-upload-token',
            'file': (io.BytesIO(b'%PDF-1.4\n'), 'invoice.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 500
    invoice_dir = (
        app.extensions['runtime_paths'].data_dir
        / 'invoice_files'
        / str(invoice_id)
    )
    assert not list(invoice_dir.glob('*'))


def test_invoice_route_rejects_allocation_count_above_limit(client):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'invoice-limit-token'

    response = client.post(
        '/invoices/new',
        data={
            'csrf_token': 'invoice-limit-token',
            'invoice_no': 'TOO-MANY-ALLOCATIONS',
            'currency': 'CNY',
            'amount_ex_tax': '100',
            'tax_amount': '13',
            'total_amount': '113',
            'allocation_count': '101',
        },
    )

    assert response.status_code == 400
    assert '发票分摊行数必须在 0 到 100 之间' in response.get_data(as_text=True)
    assert len(ledger_store.list_invoices()) == 0


def test_invoice_route_rejects_non_cny_currency(client):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'invoice-currency-token'

    response = client.post(
        '/invoices/new',
        data={
            'csrf_token': 'invoice-currency-token',
            'invoice_no': 'FOREIGN-CURRENCY',
            'currency': 'USD',
            'amount_ex_tax': '100',
            'tax_amount': '13',
            'total_amount': '113',
            'allocation_count': '0',
        },
    )

    assert response.status_code == 400
    assert '发票币种仅支持 CNY（人民币）' in response.get_data(as_text=True)
    assert len(ledger_store.list_invoices()) == 0


def test_invoice_store_rejects_non_cny_currency(tmp_db):
    with pytest.raises(ValueError, match='发票币种仅支持 CNY'):
        ledger_store.save_invoice(
            {
                'invoice_no': 'STORE-FOREIGN-CURRENCY',
                'currency': 'USD',
                'amount_ex_tax': 100,
                'tax_amount': 13,
                'total_amount': 113,
            },
            [],
        )

    assert len(ledger_store.list_invoices()) == 0


def test_issue_notice_locks_quantity_and_generates_payment(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    _rule(contract_id)
    notice_id = _notice(contract_id, item_id, 4, 1, 4, 'TZ-001')

    result = ledger_store.issue_production_notice(notice_id, '张三')

    assert result['event_id']
    assert len(result['payment_plan_ids']) == 1
    notice = ledger_store.get_production_notice(notice_id)
    assert notice['status'] == 'issued'
    assert notice['total_qty'] == 4
    assert notice['total_amount'] == 400
    item = ledger_store.list_contract_items(contract_id)[0]
    assert item['issued_qty'] == 4
    assert item['remaining_qty'] == 6
    plan = ledger_store.get_payment_plan(result['payment_plan_ids'][0])
    assert plan['due_amount'] == 120
    assert plan['calculation_base_minor'] == 40_000

    with pytest.raises(ValueError, match='只有草稿'):
        ledger_store.save_production_notice_draft(
            notice_id, {'notice_no': 'TZ-001'}, [{
                'contract_item_id': item_id, 'notice_qty': '4'
            }]
        )


def test_quantity_and_serial_ranges_are_revalidated_on_issue(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    first = _notice(contract_id, item_id, 6, 1, 6, 'TZ-001')
    ledger_store.issue_production_notice(first)

    too_many = _notice(contract_id, item_id, 5, 6, 10, 'TZ-002')
    with pytest.raises(ValueError, match='超过剩余可发数量'):
        ledger_store.issue_production_notice(too_many)

    overlap = _notice(contract_id, item_id, 4, 5, 8, 'TZ-003')
    with pytest.raises(ValueError, match='号段.*重叠'):
        ledger_store.issue_production_notice(overlap)


def test_revision_cancels_old_event_and_does_not_double_count(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    _rule(contract_id)
    original_id = _notice(contract_id, item_id, 4, 1, 4, 'TZ-REV')
    original_result = ledger_store.issue_production_notice(original_id)

    revised_id = ledger_store.revise_production_notice(original_id, '李四')
    revised = ledger_store.get_production_notice(revised_id)
    assert revised['version'] == 2
    assert revised['status'] == 'draft'
    revised_result = ledger_store.issue_production_notice(revised_id, '李四')

    assert len(revised_result['payment_plan_ids']) == 1
    assert ledger_store.get_production_notice(original_id)['status'] == 'cancelled'
    assert ledger_store.get_payment_plan(
        original_result['payment_plan_ids'][0]
    )['confirm_status'] == 'void'
    item = ledger_store.list_contract_items(contract_id)[0]
    assert item['issued_qty'] == 4
    assert item['remaining_qty'] == 6


def test_only_one_revision_draft_and_active_version_are_allowed(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    original_id = _notice(contract_id, item_id, 2, 1, 2, 'TZ-ONE-ACTIVE')
    ledger_store.issue_production_notice(original_id)

    revised_id = ledger_store.revise_production_notice(original_id)
    with pytest.raises(ValueError, match='已有第2版修订草稿'):
        ledger_store.revise_production_notice(original_id)

    ledger_store.issue_production_notice(revised_id)
    active = [
        notice for notice in ledger_store.list_production_notices(contract_id)
        if notice['status'] in {'issued', 'acknowledged', 'closed'}
    ]
    assert [(notice['version'], notice['status']) for notice in active] == [
        (2, 'issued')
    ]


def test_invoice_allocation_reconciles_contract_notice_and_payment(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    _rule(contract_id)
    notice_id = _notice(contract_id, item_id, 4, 1, 4, 'TZ-INV')
    issue = ledger_store.issue_production_notice(notice_id)
    plan_id = issue['payment_plan_ids'][0]

    invoice_id = ledger_store.save_invoice(
        {
            'invoice_code': '044001',
            'invoice_no': 'INV-001',
            'invoice_type': 'vat_special',
            'issue_date': '2026-07-22',
            'seller_name': '测试供应商',
            'seller_tax_no': 'TAX001',
            'amount_ex_tax': 100,
            'tax_amount': 13,
            'total_amount': 113,
            'tax_rate': 13,
            'review_status': 'verified',
        },
        [{
            'contract_id': contract_id,
            'production_notice_id': notice_id,
            'payment_plan_id': plan_id,
            'allocated_amount': 113,
        }],
    )

    invoice = ledger_store.get_invoice(invoice_id)
    assert invoice['allocation_status'] == 'allocated'
    assert invoice['unallocated_amount'] == 0
    assert invoice['allocations'][0]['notice_no'] == 'TZ-INV'
    assert ledger_store.list_invoices(contract_id=contract_id)[0]['id'] == invoice_id

    with pytest.raises(ValueError, match='分摊合计不能超过'):
        ledger_store.save_invoice(
            {
                **invoice,
                'amount_ex_tax': 100,
                'tax_amount': 13,
                'total_amount': 113,
            },
            [{'contract_id': contract_id, 'allocated_amount': 114}],
            invoice_id=invoice_id,
            expected_revision=invoice['revision'],
        )

    with pytest.raises(ValueError, match='已存在'):
        ledger_store.save_invoice(
            {
                'invoice_code': '044001',
                'invoice_no': 'INV-001',
                'seller_tax_no': 'TAX001',
                'amount_ex_tax': 100,
                'tax_amount': 13,
                'total_amount': 113,
            },
            [],
        )


def test_cannot_cancel_notice_after_payment(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    _rule(contract_id)
    notice_id = _notice(contract_id, item_id, 1, 1, 1, 'TZ-PAID')
    result = ledger_store.issue_production_notice(notice_id)
    plan_id = result['payment_plan_ids'][0]
    ledger_store.update_payment_plan(plan_id, {
        'confirm_status': 'confirmed',
        'paid_amount': 30,
        'paid_date': '2026-07-22',
    })

    with pytest.raises(ValueError, match='已发生付款'):
        ledger_store.cancel_production_notice(notice_id, reason='测试取消')


def test_cannot_cancel_or_revise_notice_with_invoice_allocation(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    notice_id = _notice(contract_id, item_id, 1, 1, 1, 'TZ-INVOICED')
    ledger_store.issue_production_notice(notice_id)
    ledger_store.save_invoice(
        {
            'invoice_no': 'INVOICED-NOTICE',
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [{
            'contract_id': contract_id,
            'production_notice_id': notice_id,
            'allocated_amount': 100,
        }],
    )

    with pytest.raises(ValueError, match='已有发票分摊'):
        ledger_store.cancel_production_notice(notice_id, reason='不能取消')
    with pytest.raises(ValueError, match='已有发票分摊'):
        ledger_store.revise_production_notice(notice_id)


def test_plan_only_allocation_blocks_notice_changes_and_event_recalculation(
    tmp_db,
):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    _rule(contract_id)
    notice_id = _notice(contract_id, item_id, 1, 1, 1, 'TZ-PLAN-INVOICED')
    issue = ledger_store.issue_production_notice(notice_id)
    plan_id = issue['payment_plan_ids'][0]
    ledger_store.save_invoice(
        {
            'invoice_no': 'PLAN-ONLY-ALLOCATION',
            'amount_ex_tax': 20,
            'tax_amount': 0,
            'total_amount': 20,
        },
        [{
            'contract_id': contract_id,
            'payment_plan_id': plan_id,
            'allocated_amount': 20,
        }],
    )

    with pytest.raises(ValueError, match='已有发票分摊'):
        ledger_store.cancel_production_notice(notice_id, reason='不能取消')
    with pytest.raises(ValueError, match='已有发票分摊'):
        ledger_store.revise_production_notice(notice_id)

    with pytest.raises(ValueError, match='不能小于.*有效发票分摊金额'):
        with ledger_store.get_conn() as conn:
            ledger_store._PAYMENT_RULES.create_matching_event_instances_impl(
                conn,
                contract_id=contract_id,
                event_type='production_notice_issued',
                reference_no='TZ-PLAN-INVOICED',
                event_date='2026-07-22',
                base_amount_minor=5_000,
                reference_name='投产通知 TZ-PLAN-INVOICED 第1版',
                metadata={
                    'production_notice_id': notice_id,
                    'notice_no': 'TZ-PLAN-INVOICED',
                    'version': 1,
                    'total_qty': 1,
                },
            )

    assert ledger_store.get_production_notice(notice_id)['status'] == 'issued'
    assert ledger_store.get_payment_plan(plan_id)['due_amount'] == 30
    event = next(
        item for item in ledger_store.list_payment_trigger_events(contract_id)
        if item['id'] == issue['event_id']
    )
    assert event['base_amount'] == 100


def test_invoice_notice_and_payment_must_share_event_and_respect_caps(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    _rule(contract_id)
    first = _notice(contract_id, item_id, 1, 1, 1, 'TZ-LINK-1')
    second = _notice(contract_id, item_id, 1, 2, 2, 'TZ-LINK-2')
    first_plan = ledger_store.issue_production_notice(first)['payment_plan_ids'][0]
    second_plan = ledger_store.issue_production_notice(second)['payment_plan_ids'][0]

    with pytest.raises(ValueError, match='不是由该投产通知生成'):
        ledger_store.save_invoice(
            {
                'invoice_no': 'BAD-LINK',
                'amount_ex_tax': 30,
                'tax_amount': 0,
                'total_amount': 30,
            },
            [{
                'contract_id': contract_id,
                'production_notice_id': first,
                'payment_plan_id': second_plan,
                'allocated_amount': 30,
            }],
        )

    ledger_store.save_invoice(
        {
            'invoice_no': 'CAP-1',
            'amount_ex_tax': 20,
            'tax_amount': 0,
            'total_amount': 20,
        },
        [{
            'contract_id': contract_id,
            'payment_plan_id': first_plan,
            'allocated_amount': 20,
        }],
    )
    with pytest.raises(ValueError, match='累计发票分摊不能超过应付金额'):
        ledger_store.save_invoice(
            {
                'invoice_no': 'CAP-2',
                'amount_ex_tax': 20,
                'tax_amount': 0,
                'total_amount': 20,
            },
            [{
                'contract_id': contract_id,
                'payment_plan_id': first_plan,
                'allocated_amount': 20,
            }],
        )


def test_invoice_allocation_blocks_void_and_due_reduction_on_payment_plan(
    tmp_db,
):
    contract_id = _contract()
    plan_id = ledger_store.insert_payment_plan(contract_id, {
        'phase_name': '已核销付款节点',
        'due_amount': 100,
        'confirm_status': 'confirmed',
    })
    ledger_store.save_invoice(
        {
            'invoice_no': 'PLAN-REVERSE-GUARD',
            'amount_ex_tax': 80,
            'tax_amount': 0,
            'total_amount': 80,
        },
        [{
            'contract_id': contract_id,
            'payment_plan_id': plan_id,
            'allocated_amount': 80,
        }],
    )

    with pytest.raises(ValueError, match='有效发票分摊.*不能作废'):
        ledger_store.save_payment_plan_changes(contract_id, [{
            'id': plan_id,
            'data': {'confirm_status': 'void'},
        }])
    with pytest.raises(ValueError, match='不能小于.*有效发票分摊金额'):
        ledger_store.update_payment_plan(plan_id, {'due_amount': 79.99})

    assert ledger_store.update_payment_plan(
        plan_id, {'due_amount': 80}
    ) == 1
    plan = ledger_store.get_payment_plan(plan_id)
    assert plan['confirm_status'] == 'confirmed'
    assert plan['due_amount'] == 80


def test_event_reference_collision_is_rejected_before_notice_issue(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    rule_id = _rule(contract_id)
    ledger_store.create_payment_rule_event_instance(
        contract_id, rule_id, 'TZ-COLLISION', base_amount=100
    )
    notice_id = _notice(contract_id, item_id, 2, 1, 2, 'TZ-COLLISION')

    with pytest.raises(ValueError, match='已被其他来源占用'):
        ledger_store.issue_production_notice(notice_id)
    assert ledger_store.get_production_notice(notice_id)['status'] == 'draft'


def test_invoice_state_machine_requires_full_allocation_and_excludes_void(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    notice_id = _notice(contract_id, item_id, 1, 1, 1, 'TZ-STATE')
    ledger_store.issue_production_notice(notice_id)

    with pytest.raises(ValueError, match='必须全额分摊'):
        ledger_store.save_invoice(
            {
                'invoice_no': 'PARTIAL-VERIFIED',
                'amount_ex_tax': 100,
                'tax_amount': 0,
                'total_amount': 100,
                'review_status': 'verified',
            },
            [{'contract_id': contract_id, 'allocated_amount': 0.01}],
        )

    invoice_id = ledger_store.save_invoice(
        {
            'invoice_no': 'TO-VOID',
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [{
            'contract_id': contract_id,
            'production_notice_id': notice_id,
            'allocated_amount': 100,
        }],
    )
    invoice = ledger_store.get_invoice(invoice_id)
    invoice['invoice_status'] = 'void'
    ledger_store.save_invoice(
        invoice, [], invoice_id=invoice_id,
        expected_revision=invoice['revision'],
    )
    assert ledger_store.get_production_notice(notice_id)['allocated_amount'] == 0


def test_full_red_invoice_offsets_original_allocation(tmp_db):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    notice_id = _notice(contract_id, item_id, 1, 1, 1, 'TZ-RED')
    ledger_store.issue_production_notice(notice_id)
    original_id = ledger_store.save_invoice(
        {
            'invoice_no': 'ORIGINAL',
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [{
            'contract_id': contract_id,
            'production_notice_id': notice_id,
            'allocated_amount': 100,
        }],
    )
    assert ledger_store.get_production_notice(notice_id)['allocated_amount'] == 100

    red_id = ledger_store.save_invoice(
        {
            'invoice_no': 'RED-OFFSET',
            'invoice_status': 'red',
            'original_invoice_id': original_id,
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [],
    )
    assert ledger_store.get_production_notice(notice_id)['allocated_amount'] == 0

    original = ledger_store.get_invoice(original_id)
    original['amount_ex_tax'] = 200
    original['total_amount'] = 200
    with pytest.raises(ValueError, match='已有生效红字发票'):
        ledger_store.save_invoice(
            original,
            original['allocations'],
            invoice_id=original_id,
            expected_revision=original['revision'],
        )

    original = ledger_store.get_invoice(original_id)
    original['invoice_status'] = 'void'
    with pytest.raises(ValueError, match='已有生效红字发票'):
        ledger_store.save_invoice(
            original, [], invoice_id=original_id,
            expected_revision=original['revision'],
        )

    with ledger_store.get_conn() as conn, pytest.raises(
        sqlite3.IntegrityError,
        match='已有生效红字发票',
    ):
        conn.execute(
            'UPDATE invoices SET total_amount_minor = 20000 WHERE id = ?',
            (original_id,),
        )

    assert ledger_store.get_invoice(original_id)['total_amount'] == 100
    assert ledger_store.get_invoice(red_id)['total_amount'] == 100
    ledger_store.cancel_production_notice(notice_id, reason='发票已全额红冲')
    assert ledger_store.get_production_notice(notice_id)['status'] == 'cancelled'


def test_effective_red_invoice_cannot_be_voided_or_retargeted(tmp_db):
    contract_id = _contract()
    plan_id = ledger_store.insert_payment_plan(contract_id, {
        'phase_name': '红冲后可降额节点',
        'due_amount': 100,
        'confirm_status': 'confirmed',
    })
    original_id = ledger_store.save_invoice(
        {
            'invoice_no': 'RED-LOCK-ORIGINAL',
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [{
            'contract_id': contract_id,
            'payment_plan_id': plan_id,
            'allocated_amount': 100,
        }],
    )
    alternate_id = ledger_store.save_invoice(
        {
            'invoice_no': 'RED-LOCK-ALTERNATE',
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [],
    )
    red_id = ledger_store.save_invoice(
        {
            'invoice_no': 'RED-LOCK',
            'invoice_status': 'red',
            'original_invoice_id': original_id,
            'amount_ex_tax': 100,
            'tax_amount': 0,
            'total_amount': 100,
        },
        [],
    )
    assert ledger_store.update_payment_plan(plan_id, {'due_amount': 0}) == 1

    red_invoice = ledger_store.get_invoice(red_id)
    red_invoice['invoice_status'] = 'void'
    red_invoice['original_invoice_id'] = None
    with pytest.raises(ValueError, match='已生效红字发票不能变更'):
        ledger_store.save_invoice(
            red_invoice, [], invoice_id=red_id,
            expected_revision=red_invoice['revision'],
        )

    red_invoice = ledger_store.get_invoice(red_id)
    red_invoice['original_invoice_id'] = alternate_id
    with pytest.raises(ValueError, match='已生效红字发票不能变更'):
        ledger_store.save_invoice(
            red_invoice, [], invoice_id=red_id,
            expected_revision=red_invoice['revision'],
        )

    stored_red = ledger_store.get_invoice(red_id)
    assert stored_red['invoice_status'] == 'red'
    assert stored_red['original_invoice_id'] == original_id
    assert ledger_store.get_invoice(original_id)['has_red_offset'] == 1
    assert ledger_store.get_payment_plan(plan_id)['due_amount'] == 0


def test_contract_item_ranges_history_and_deleted_contract_guard(tmp_db):
    contract_id = _contract()
    item_id = ledger_store.save_contract_items(
        contract_id,
        [{
            'line_no': 1,
            'item_name': '有号段产品',
            'contracted_qty': 3,
            'serial_start': 10,
            'serial_end': 12,
            'unit_price': 5,
        }],
        operator='张三',
    )[0]
    item = ledger_store.get_contract_item(item_id, contract_id)
    assert (item['serial_start'], item['serial_end']) == (10, 12)
    history = ledger_store.list_contract_item_history(contract_id)
    assert history[0]['action'] == 'create'
    assert history[0]['operator'] == '张三'

    ledger_store.soft_delete_contract(contract_id)
    with pytest.raises(ValueError, match='已删除'):
        ledger_store.save_contract_items(
            contract_id,
            [{
                'id': item_id,
                'line_no': 1,
                'item_name': '有号段产品',
                'contracted_qty': 3,
            }],
        )


def test_contract_item_line_numbers_can_be_swapped_atomically(tmp_db):
    contract_id = _contract()
    first, second = ledger_store.save_contract_items(contract_id, [
        {'line_no': 1, 'item_name': '产品一', 'contracted_qty': 1},
        {'line_no': 2, 'item_name': '产品二', 'contracted_qty': 1},
    ])

    ledger_store.save_contract_items(contract_id, [
        {'id': first, 'line_no': 2, 'item_name': '产品一', 'contracted_qty': 1},
        {'id': second, 'line_no': 1, 'item_name': '产品二', 'contracted_qty': 1},
    ])

    assert [(row['id'], row['line_no']) for row in ledger_store.list_contract_items(
        contract_id
    )] == [(second, 1), (first, 2)]


def test_invoice_business_key_is_enforced_by_database(tmp_db):
    contract_id = _contract()
    invoice_id = ledger_store.save_invoice(
        {
            'invoice_no': 'DB-UNIQUE',
            'seller_tax_no': 'UNIQUE-TAX',
            'amount_ex_tax': 1,
            'tax_amount': 0,
            'total_amount': 1,
        },
        [{'contract_id': contract_id, 'allocated_amount': 1}],
    )
    assert invoice_id
    with ledger_store.get_conn() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO invoices (
                   invoice_no, seller_tax_no, amount_ex_tax_minor,
                   tax_amount_minor, total_amount_minor, created_at, updated_at
               ) VALUES ('DB-UNIQUE', 'UNIQUE-TAX', 100, 0, 100, 'x', 'x')"""
        )


def test_production_and_invoice_pages_render(client):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    notice_id = _notice(contract_id, item_id, 2, 1, 2, 'TZ-UI')
    invoice_id = ledger_store.save_invoice(
        {
            'invoice_no': 'INV-UI',
            'amount_ex_tax': 10,
            'tax_amount': 1.3,
            'total_amount': 11.3,
        },
        [{'contract_id': contract_id, 'allocated_amount': 11.3}],
    )

    for path in (
        f'/contracts/{contract_id}',
        f'/contracts/{contract_id}?tab=production',
        f'/contracts/{contract_id}?tab=invoices',
        f'/contracts/{contract_id}/items',
        f'/contracts/{contract_id}/production-notices/new',
        '/production-notices',
        f'/production-notices/{notice_id}',
        '/invoices',
        '/invoices/new',
        f'/invoices/{invoice_id}',
        f'/invoices/{invoice_id}/edit',
    ):
        response = client.get(path)
        assert response.status_code == 200, path


def test_paginated_ledgers_and_invoice_target_api(client):
    contract_id = _contract()
    item_id = _baseline(contract_id)
    issued_id = _notice(contract_id, item_id, 1, 1, 1, 'TZ-PAGE-1')
    ledger_store.issue_production_notice(issued_id)
    _notice(contract_id, item_id, 1, 2, 2, 'TZ-PAGE-2')
    for suffix in ('1', '2'):
        ledger_store.save_invoice(
            {
                'invoice_no': f'INV-PAGE-{suffix}',
                'amount_ex_tax': 1,
                'tax_amount': 0,
                'total_amount': 1,
            },
            [{'contract_id': contract_id, 'allocated_amount': 1}],
        )

    notices = ledger_store.list_production_notices(
        contract_id=contract_id, page=1, per_page=1
    )
    invoices = ledger_store.list_invoices(
        contract_id=contract_id, page=2, per_page=1
    )
    assert (notices['total'], notices['pages'], len(notices['rows'])) == (2, 2, 1)
    assert (invoices['total'], invoices['page'], len(invoices['rows'])) == (2, 2, 1)
    notice_summary = ledger_store.summarize_production_notices(contract_id=contract_id)
    invoice_summary = ledger_store.summarize_invoices(contract_id=contract_id)
    assert notice_summary == {
        'count': 2, 'active_count': 1, 'total_qty': 1, 'total_amount': 100.0,
    }
    assert invoice_summary['count'] == 2
    assert invoice_summary['valid_total'] == 2
    assert invoice_summary['unallocated_amount'] == 0

    response = client.get(f'/api/contracts/{contract_id}/invoice-targets')
    assert response.status_code == 200
    assert [row['id'] for row in response.get_json()['notices']] == [issued_id]

    ledger_store.soft_delete_contract(contract_id)
    response = client.get(f'/api/contracts/{contract_id}/invoice-targets')
    assert response.status_code == 404
