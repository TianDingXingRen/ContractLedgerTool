from datetime import date, timedelta


def test_dashboard_queries_match_public_wrappers(tmp_db):
    import ledger_store
    from ledger_store import dashboard_queries

    today = date.today()
    soon = (today + timedelta(days=3)).strftime('%Y-%m-%d')
    later = (today + timedelta(days=40)).strftime('%Y-%m-%d')

    active_id = ledger_store.create_contract(
        {
            'contract_no': 'DASH-001',
            'title': 'Dashboard Active',
            'status': 'active',
            'amount': 1000,
            'expiry_date': soon,
        },
        {},
        '/active.docx',
    )
    draft_id = ledger_store.create_contract(
        {
            'contract_no': 'DASH-002',
            'title': 'Dashboard Draft',
            'status': 'draft',
            'amount': 500,
            'expiry_date': later,
        },
        {},
        '/draft.docx',
    )
    ledger_store.insert_payment_plan(
        active_id,
        {
            'phase_name': 'Due soon',
            'due_amount': 300,
            'paid_amount': 100,
            'paid_date': today.strftime('%Y-%m-%d'),
            'confirm_status': 'confirmed',
            'due_date': soon,
        },
    )
    ledger_store.insert_payment_plan(
        draft_id,
        {
            'phase_name': 'Pending review',
            'due_amount': 200,
            'confirm_status': 'pending',
        },
    )

    assert ledger_store.get_contract_stats() == dashboard_queries.get_contract_stats(
        ledger_store.get_conn
    )
    assert ledger_store.get_payment_stats() == dashboard_queries.get_payment_stats(
        ledger_store.get_conn
    )
    assert ledger_store.get_due_soon_payments(days=7) == (
        dashboard_queries.get_due_soon_payments(
            ledger_store.get_conn, ledger_store.row_to_dict, days=7
        )
    )

    stats = ledger_store.get_payment_stats()
    assert stats['total_due'] == 300
    assert stats['total_paid'] == 100
    assert stats['total_unpaid'] == 200
    assert stats['pending_count'] == 1

    expiring_ids = {row['id'] for row in ledger_store.get_expiring_contracts(days=7)}
    assert active_id in expiring_ids
    assert draft_id not in expiring_ids


def test_monthly_and_recent_dashboard_queries(tmp_db):
    import ledger_store
    from ledger_store import dashboard_queries

    contract_id = ledger_store.create_contract(
        {
            'contract_no': 'DASH-003',
            'title': 'Monthly Contract',
            'status': 'signed',
            'amount': 1200,
        },
        {},
        '/monthly.docx',
    )
    ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': 'April',
            'due_amount': 400,
            'paid_amount': 150,
            'paid_date': '2030-04-01',
            'confirm_status': 'confirmed',
            'due_date': '2030-04-10',
        },
    )

    assert ledger_store.get_monthly_payments(2030, 4) == (
        dashboard_queries.get_monthly_payments(ledger_store.get_conn, 2030, 4)
    )
    assert ledger_store.get_monthly_payments(2030, 4) == {
        'count': 1,
        'amount': 250,
    }
    assert ledger_store.next_month_payment_plans('2030-04-01', '2030-04-30') == (
        dashboard_queries.next_month_payment_plans(
            ledger_store.get_conn,
            ledger_store.row_to_dict,
            '2030-04-01',
            '2030-04-30',
        )
    )
    assert ledger_store.get_recent_contracts(1)[0]['id'] == contract_id
