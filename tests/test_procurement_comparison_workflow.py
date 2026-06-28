def _project_supplier_item(procurement_store):
    project_id = procurement_store.create_project({
        'project_no': 'CW-001',
        'project_name': '比价澄清测试',
    })
    item_id = procurement_store.add_project_item(project_id, {
        'item_name': '结构件A',
        'quantity_text': '10',
        'unit': '件',
    })
    supplier_id = procurement_store.add_project_supplier(project_id, {
        'supplier_name': '供应商A',
    })
    return project_id, supplier_id, item_id


def _project_supplier_item_quote(procurement_store):
    project_id, supplier_id, item_id = _project_supplier_item(procurement_store)
    job_id = procurement_store.create_import_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'original_name': 'comparison-quote.xlsx',
        'relative_path': 'procurement/CW-001/comparison-quote.xlsx',
        'file_sha256': 'comparison-quote-hash',
        'payload': {
            'header': {
                'total_amount_minor': 10000,
                'currency': 'CNY',
                'quote_date': '2030-01-01',
            },
            'items': [{
                'project_item_id': item_id,
                'line_no': 1,
                'item_name': 'item-a',
                'quantity_text': '10',
                'unit': 'pcs',
                'unit_price_minor': 1000,
                'amount_minor': 10000,
            }],
        },
        'errors': [],
        'warnings': [],
    })
    quote_id = procurement_store.confirm_import_job(job_id)
    return project_id, supplier_id, item_id, quote_id


def test_comparison_and_clarification_workflow_matches_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import comparison_workflow

    procurement_store.init_db()
    project_id, supplier_id, item_id, quote_id = _project_supplier_item_quote(procurement_store)
    run_id = procurement_store.create_comparison_run(
        project_id,
        quote_ids=[quote_id],
        rule_config={'price_threshold_percent': '20'},
        results=[{
            'project_item_id': item_id,
            'supplier_id': supplier_id,
            'quote_id': quote_id,
            'result_type': 'price_gap',
            'description': '单价偏高',
            'severity': 'high',
            'suggestion': '请澄清报价',
            'metric': {'gap_percent': 25},
        }],
    )

    latest = procurement_store.get_latest_comparison(project_id)
    assert latest == comparison_workflow.get_latest_comparison(
        ledger_store.get_conn, project_id
    )
    assert latest['id'] == run_id
    assert latest['quote_ids'] == [quote_id]
    assert latest['rule_config'] == {'price_threshold_percent': '20'}
    assert latest['results'][0]['supplier_name'] == '供应商A'
    assert latest['results'][0]['item_name'] == '结构件A'

    result_id = latest['results'][0]['id']
    created = procurement_store.create_clarifications_from_results(project_id, [{
        'supplier_id': supplier_id,
        'project_item_id': item_id,
        'question_type': 'price',
        'question_text': '请说明价格差异',
        'source_result_id': result_id,
    }])
    assert created == 1
    assert procurement_store.get_project(project_id)['status'] == 'clarifying'
    assert procurement_store.list_clarifications(project_id) == (
        comparison_workflow.list_clarifications(ledger_store.get_conn, project_id)
    )
    question = procurement_store.list_clarifications(project_id)[0]
    assert question['supplier_name'] == '供应商A'

    procurement_store.update_clarification(question['id'], {
        'status': 'replied',
        'answer_text': '已调整',
    })
    updated = procurement_store.list_clarifications(project_id)[0]
    assert updated['status'] == 'replied'
    assert updated['answer_text'] == '已调整'


def test_rule_config_workflow_matches_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import comparison_workflow

    procurement_store.init_db()
    project_id, _supplier_id, _item_id = _project_supplier_item(procurement_store)

    assert procurement_store.get_rule_config(project_id) == {
        'project_id': project_id,
        'price_threshold_percent': '20',
        'min_valid_suppliers': 2,
        'require_same_price_basis': 1,
    }

    procurement_store.save_rule_config(project_id, {
        'price_threshold_percent': '15.5',
        'min_valid_suppliers': 3,
        'require_same_price_basis': False,
    })

    assert procurement_store.get_rule_config(project_id) == (
        comparison_workflow.get_rule_config(
            ledger_store.get_conn, procurement_store._dict, project_id
        )
    )
    config = procurement_store.get_rule_config(project_id)
    assert config['price_threshold_percent'] == '15.5'
    assert config['min_valid_suppliers'] == 3
    assert config['require_same_price_basis'] == 0
