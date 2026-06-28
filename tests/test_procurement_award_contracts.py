def _project_quote_item(procurement_store):
    project_id = procurement_store.create_project({
        'project_no': 'AC-001',
        'project_name': '成交合同测试',
    })
    item_id = procurement_store.add_project_item(project_id, {
        'item_name': '结构件A',
        'quantity_text': '10',
        'unit': '件',
    })
    supplier_id = procurement_store.add_project_supplier(project_id, {
        'supplier_name': '供应商A',
    })
    job_id = procurement_store.create_import_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'original_name': 'quote.xlsx',
        'relative_path': 'procurement/AC-001/quote.xlsx',
        'file_sha256': 'award-quote-hash',
        'payload': {
            'header': {
                'total_amount_minor': 10000,
                'currency': 'CNY',
                'quote_date': '2030-01-01',
            },
            'items': [{
                'project_item_id': item_id,
                'line_no': 1,
                'item_name': '结构件A',
                'quantity_text': '10',
                'unit': '件',
                'unit_price_minor': 1000,
                'amount_minor': 10000,
            }],
        },
        'errors': [],
        'warnings': [],
    })
    quote_id = procurement_store.confirm_import_job(job_id)
    quote_item = procurement_store.get_quote_items(quote_id)[0]
    return project_id, supplier_id, quote_id, quote_item


def test_award_and_contract_link_workflow_matches_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import award_contracts

    procurement_store.init_db()
    project_id, supplier_id, quote_id, quote_item = _project_quote_item(procurement_store)
    recommendation_id = procurement_store.create_award_recommendation(
        project_id,
        supplier_id,
        quote_id,
        {
            'recommended_amount_minor': 10000,
            'reason_summary': '综合评分最高',
            'currency': 'CNY',
        },
        [quote_item],
    )

    assert procurement_store.get_latest_award(project_id) == award_contracts.get_latest_award(
        ledger_store.get_conn, project_id
    )
    award = procurement_store.get_latest_award(project_id)
    assert award['id'] == recommendation_id
    assert award['items'][0]['quote_item_id'] == quote_item['id']
    assert procurement_store.get_project(project_id)['status'] == 'award_confirmed'

    sheet = procurement_store.get_or_create_contract_data_sheet(
        project_id,
        recommendation_id,
        {'supplier': '供应商A', 'amount': 10000},
    )
    assert procurement_store.get_or_create_contract_data_sheet(
        project_id, recommendation_id, {'ignored': True}
    )['id'] == sheet['id']
    assert procurement_store.get_contract_data_sheet(sheet['id']) == (
        award_contracts.get_contract_data_sheet(
            ledger_store.get_conn, procurement_store._dict, sheet['id']
        )
    )
    assert procurement_store.get_contract_data_sheet(sheet['id'])['payload']['supplier'] == '供应商A'

    procurement_store.mark_data_sheet_in_editor(sheet['id'])
    assert procurement_store.get_contract_data_sheet(sheet['id'])['status'] == 'in_editor'

    contract_id = ledger_store.create_contract({
        'contract_no': 'AC-CONTRACT-001',
        'title': '成交合同',
    }, {}, '/ac-contract.docx')
    link_id = procurement_store.complete_contract_link(sheet['id'], contract_id)
    assert procurement_store.complete_contract_link(sheet['id'], contract_id) == link_id
    assert procurement_store.get_project(project_id)['status'] == 'contract_created'
    assert procurement_store.get_project_contract_links(project_id) == (
        award_contracts.get_project_contract_links(ledger_store.get_conn, project_id)
    )
    links = procurement_store.get_project_contract_links(project_id)
    assert links[0]['contract_id'] == contract_id
    assert links[0]['source_type'] == 'award'


def test_split_award_and_direct_contract_ref_match_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import award_contracts

    procurement_store.init_db()
    project_id, supplier_id, quote_id, quote_item = _project_quote_item(procurement_store)
    split_id = procurement_store.create_split_award_recommendation(
        project_id,
        {'reason_summary': '按分项最低价成交'},
        [{**quote_item, 'supplier_id': supplier_id, 'supplier_name': '供应商A', 'quote_id': quote_id}],
    )
    assert procurement_store.get_latest_award(project_id) == award_contracts.get_latest_award(
        ledger_store.get_conn, project_id
    )
    assert procurement_store.get_latest_award(project_id)['id'] == split_id
    assert procurement_store.get_latest_award(project_id)['is_split'] == 1

    contract_id = ledger_store.create_contract({
        'contract_no': 'AC-DIRECT-001',
        'title': '直接合同',
    }, {}, '/ac-direct.docx')
    procurement_store.add_contract_ref(project_id, contract_id)

    links = procurement_store.get_project_contract_links(project_id)
    assert links == award_contracts.get_project_contract_links(ledger_store.get_conn, project_id)
    assert links[0]['contract_id'] == contract_id
    assert links[0]['source_type'] == 'direct_contract'
