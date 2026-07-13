import pytest


def _project_with_supplier_and_item(procurement_store):
    project_id = procurement_store.create_project({
        'project_no': 'QJ-001',
        'project_name': '报价任务测试',
        'owner': '采购员',
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


def _quote_payload(item_id):
    return {
        'header': {
            'quote_date': '2030-07-01',
            'quote_valid_until': '2030-08-01',
            'total_amount_minor': 12345,
            'currency': 'CNY',
            'tax_rate_bps': 1300,
            'price_basis': 'tax_inclusive',
            'delivery_period': '30天',
            'payment_terms': '验收后付款',
        },
        'items': [{
            'project_item_id': item_id,
            'line_no': 1,
            'item_name': '结构件A',
            'quantity_text': '10',
            'unit': '件',
            'unit_price_minor': 1234,
            'amount_minor': 12345,
        }],
        'size_bytes': 42,
    }


def test_quote_import_and_quote_queries_match_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import quote_jobs

    procurement_store.init_db()
    project_id, supplier_id, item_id = _project_with_supplier_and_item(procurement_store)
    job_id = procurement_store.create_import_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'original_name': 'quote.xlsx',
        'relative_path': 'procurement/QJ-001/quotes/quote.xlsx',
        'file_sha256': 'quote-hash',
        'parser_version': 'test',
        'payload': _quote_payload(item_id),
        'errors': [],
        'warnings': ['提示'],
    })

    assert procurement_store.get_import_job(job_id) == quote_jobs.get_import_job(
        ledger_store.get_conn, procurement_store._dict, job_id
    )
    assert procurement_store.get_import_job(job_id)['warnings'] == ['提示']

    quote_id = procurement_store.confirm_import_job(job_id)

    assert procurement_store.confirm_import_job(job_id) == quote_id
    assert procurement_store.get_project(project_id)['status'] == 'quotes_received'
    assert procurement_store.get_project_supplier(supplier_id)['quote_status'] == 'received'
    assert procurement_store.list_quotes(project_id) == quote_jobs.list_quotes(
        ledger_store.get_conn, project_id
    )
    assert procurement_store.get_latest_quotes(project_id) == quote_jobs.get_latest_quotes(
        ledger_store.get_conn, project_id
    )
    assert procurement_store.get_quote(quote_id) == quote_jobs.get_quote(
        ledger_store.get_conn, procurement_store._dict, quote_id
    )
    assert procurement_store.get_quote_items(quote_id) == quote_jobs.get_quote_items(
        ledger_store.get_conn, quote_id
    )

    quote = procurement_store.get_quote(quote_id)
    assert quote['supplier_name'] == '供应商A'
    assert quote['total_amount_minor'] == 12345
    assert procurement_store.get_quote_items(quote_id)[0]['project_item_id'] == item_id

    with pytest.raises(ValueError, match='确认报价'):
        procurement_store.delete_project_supplier(project_id, supplier_id)

    try:
        procurement_store.create_import_job({
            'project_id': project_id,
            'supplier_id': supplier_id,
            'quote_round': 2,
            'original_name': 'quote-copy.xlsx',
            'relative_path': 'procurement/QJ-001/quotes/quote-copy.xlsx',
            'file_sha256': 'quote-hash',
            'payload': _quote_payload(item_id),
        })
    except ValueError as exc:
        assert '已经导入' in str(exc)
    else:
        raise AssertionError('confirmed quote file hash should not be imported twice')


def test_quote_mapping_jobs_match_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import quote_jobs

    procurement_store.init_db()
    project_id, supplier_id, _item_id = _project_with_supplier_and_item(procurement_store)
    mapping_id = procurement_store.create_mapping_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'source_type': 'xlsx',
        'original_name': 'custom.xlsx',
        'relative_path': 'procurement/QJ-001/mapping/custom.xlsx',
        'file_sha256': 'mapping-hash',
        'source': {'tables': [{'name': '报价表'}]},
    })

    assert procurement_store.get_mapping_job(mapping_id) == quote_jobs.get_mapping_job(
        ledger_store.get_conn, procurement_store._dict, mapping_id
    )
    assert procurement_store.get_mapping_job(mapping_id)['source'] == {
        'tables': [{'name': '报价表'}],
    }

    procurement_store.update_mapping_job(
        mapping_id,
        {'item_name': 0, 'unit_price': 1},
        {'table_name': '报价表'},
    )
    parsed = procurement_store.get_mapping_job(mapping_id)
    assert parsed['status'] == 'parsed'
    assert parsed['column_map'] == {'item_name': 0, 'unit_price': 1}
    assert parsed['metadata'] == {'table_name': '报价表'}

    procurement_store.mark_mapping_job_confirmed(mapping_id)
    assert procurement_store.get_mapping_job(mapping_id)['status'] == 'confirmed'
