def test_contract_list_query_wrapper_matches_extracted_module(tmp_db):
    import ledger_store
    from ledger_store import list_queries

    active_id = ledger_store.create_contract(
        {
            'contract_no': 'LIST-001',
            'title': '列表查询合同',
            'status': 'signed',
            'owner': 'Alice',
            'project_name': '列表项目',
        },
        {},
        '/list-001.docx',
    )
    deleted_id = ledger_store.create_contract(
        {
            'contract_no': 'LIST-002',
            'title': '回收站合同',
            'status': 'draft',
            'owner': 'Bob',
        },
        {},
        '/list-002.docx',
    )
    ledger_store.insert_payment_plan(
        active_id,
        {
            'phase_name': 'Phoenix milestone',
            'due_amount': 100,
            'confirm_status': 'confirmed',
        },
    )
    ledger_store.soft_delete_contract(deleted_id)

    public_result = ledger_store.list_contracts(q='Phoenix', per_page=10)
    direct_result = list_queries.list_contracts(
        ledger_store.get_conn,
        ledger_store.row_to_dict,
        q='Phoenix',
        per_page=10,
    )
    assert public_result == direct_result
    assert public_result['total'] == 1
    assert public_result['rows'][0]['id'] == active_id
    assert public_result['rows'][0]['plan_count'] == 1
    assert public_result['rows'][0]['payable_count'] == 1

    assert ledger_store.list_contracts(include_deleted=True, per_page=10)['total'] == 2
    trash = ledger_store.list_contracts(deleted_only=True, per_page=10)
    assert trash['total'] == 1
    assert trash['rows'][0]['id'] == deleted_id


def test_payment_plan_list_query_wrapper_matches_extracted_module(tmp_db):
    import ledger_store
    from ledger_store import list_queries

    contract_id = ledger_store.create_contract(
        {
            'contract_no': 'PAY-LIST-001',
            'title': '付款列表合同',
            'status': 'active',
            'amount': 1000,
            'project_name': '付款项目',
            'coverage_start': 1,
            'coverage_end': 12,
        },
        {},
        '/pay-list-001.docx',
    )
    ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '首付款',
            'due_amount': 300,
            'confirm_status': 'confirmed',
            'due_date': '2030-05-10',
        },
    )
    ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '尾款',
            'due_amount': 700,
            'confirm_status': 'pending',
            'due_date': '2030-06-10',
        },
    )

    public_rows = ledger_store.list_payment_plans(
        project_name='付款项目',
        confirm_status='confirmed',
    )
    direct_rows = list_queries.list_payment_plans(
        ledger_store.get_conn,
        ledger_store.row_to_dict,
        project_name='付款项目',
        confirm_status='confirmed',
    )
    assert public_rows == direct_rows
    assert len(public_rows) == 1
    assert public_rows[0]['contract_no'] == 'PAY-LIST-001'
    assert public_rows[0]['coverage_start'] == 1
    assert public_rows[0]['coverage_end'] == 12

    public_page = ledger_store.list_payment_plans(
        contract_id=contract_id,
        page=1,
        per_page=1,
    )
    direct_page = list_queries.list_payment_plans(
        ledger_store.get_conn,
        ledger_store.row_to_dict,
        contract_id=contract_id,
        page=1,
        per_page=1,
    )
    assert public_page == direct_page
    assert public_page['total'] == 2
    assert public_page['pages'] == 2
    assert public_page['rows'][0]['phase_name'] == '首付款'
