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


def test_confirmed_quote_files_receive_monotonic_project_versions(tmp_db):
    import procurement_store

    procurement_store.init_db()
    project_id, supplier_id, item_id = _project_with_supplier_and_item(
        procurement_store
    )

    quote_ids = []
    for quote_round in (1, 2):
        job_id = procurement_store.create_import_job({
            'project_id': project_id,
            'supplier_id': supplier_id,
            'quote_round': quote_round,
            'original_name': f'quote-{quote_round}.xlsx',
            'relative_path': (
                f'procurement/QJ-001/quotes/quote-{quote_round}.xlsx'
            ),
            'file_sha256': f'quote-hash-{quote_round}',
            'parser_version': 'test',
            'payload': _quote_payload(item_id),
            'errors': [],
            'warnings': [],
        })
        quote_ids.append(procurement_store.confirm_import_job(job_id))

    files = sorted(
        (
            row for row in procurement_store.list_project_files(project_id)
            if row['file_type'] == 'supplier_quote'
        ),
        key=lambda row: row['version'],
    )
    assert [row['version'] for row in files] == [1, 2]
    assert [row['relative_path'] for row in files] == [
        'procurement/QJ-001/quotes/quote-1.xlsx',
        'procurement/QJ-001/quotes/quote-2.xlsx',
    ]
    assert [
        procurement_store.get_quote(quote_id)['original_file_id']
        for quote_id in quote_ids
    ] == [row['id'] for row in files]


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


def test_confirmed_quote_update_delete_and_derived_state(tmp_db):
    import ledger_store
    import procurement_store

    procurement_store.init_db()
    project_id, supplier_id, item_id = _project_with_supplier_and_item(procurement_store)
    job_id = procurement_store.create_import_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'original_name': 'editable.xlsx',
        'relative_path': 'QJ-001/04_供应商报价/editable.xlsx',
        'file_sha256': 'editable-hash',
        'parser_version': 'test',
        'payload': _quote_payload(item_id),
        'errors': [],
        'warnings': [],
    })
    quote_id = procurement_store.confirm_import_job(job_id)
    quote_item = procurement_store.get_quote_items(quote_id)[0]
    procurement_store.create_comparison_run(
        project_id, [quote_id], {'threshold_percent': 20}, []
    )
    assert procurement_store.get_latest_comparison(project_id)

    with pytest.raises(ValueError, match='明细与原导入记录不一致'):
        procurement_store.update_quote(
            quote_id,
            {'price_basis': 'tax_inclusive'},
            [
                {'id': quote_item['id'], 'unit_price_minor': 1500, 'amount_minor': 15000},
                {'id': quote_item['id'], 'unit_price_minor': 1500, 'amount_minor': 15000},
            ],
        )

    procurement_store.update_quote(
        quote_id,
        {
            'quote_date': '2030-07-02',
            'quote_valid_until': '2030-09-01',
            'tax_rate_bps': 900,
            'price_basis': 'tax_exclusive',
            'delivery_period': '20天',
            'payment_terms': '验收后60天付款',
            'warranty_period': '两年',
            'package_transport': '供应商承担',
            'technical_deviation': '无',
            'commercial_deviation': '无',
        },
        [{
            'id': quote_item['id'],
            'unit_price_minor': 1500,
            'amount_minor': 15000,
            'delivery_period': '15天',
            'technical_deviation': '技术说明',
            'commercial_deviation': '',
            'remark': '人工复核',
        }],
    )

    updated = procurement_store.get_quote(quote_id)
    assert updated['total_amount_minor'] == 15000
    assert updated['tax_rate_bps'] == 900
    assert updated['price_basis'] == 'tax_exclusive'
    assert updated['delivery_period'] == '20天'
    updated_item = procurement_store.get_quote_items(quote_id)[0]
    assert updated_item['unit_price_minor'] == 1500
    assert updated_item['remark'] == '人工复核'
    assert procurement_store.get_latest_comparison(project_id) is None

    result = procurement_store.delete_quote(quote_id)
    assert result == {
        'project_id': project_id,
        'relative_path': 'QJ-001/04_供应商报价/editable.xlsx',
    }
    assert procurement_store.get_quote(quote_id) is None
    assert procurement_store.get_quote_items(quote_id) == []
    assert procurement_store.get_import_job(job_id)['status'] == 'cancelled'
    assert procurement_store.get_project_supplier(supplier_id)['quote_status'] == 'pending'
    assert procurement_store.get_project(project_id)['status'] == 'documents_ready'
    assert procurement_store.list_project_files(project_id) == []
    with ledger_store.get_conn() as conn:
        actions = [
            row[0] for row in conn.execute(
                """SELECT action FROM procurement_audit_events
                   WHERE entity_type = 'supplier_quote' AND entity_id = ? ORDER BY id""",
                (quote_id,),
            ).fetchall()
        ]
    assert actions == ['confirm_import', 'update', 'delete']

    replacement_job = procurement_store.create_import_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'original_name': 'editable-again.xlsx',
        'relative_path': 'QJ-001/04_供应商报价/editable-again.xlsx',
        'file_sha256': 'editable-hash',
        'payload': _quote_payload(item_id),
    })
    assert replacement_job != job_id


def test_award_link_locks_confirmed_quote(tmp_db):
    import procurement_store

    procurement_store.init_db()
    project_id, supplier_id, item_id = _project_with_supplier_and_item(procurement_store)
    job_id = procurement_store.create_import_job({
        'project_id': project_id,
        'supplier_id': supplier_id,
        'quote_round': 1,
        'original_name': 'locked.xlsx',
        'relative_path': 'QJ-001/04_供应商报价/locked.xlsx',
        'file_sha256': 'locked-hash',
        'payload': _quote_payload(item_id),
    })
    quote_id = procurement_store.confirm_import_job(job_id)
    quote_item = procurement_store.get_quote_items(quote_id)[0]
    procurement_store.create_award_recommendation(
        project_id,
        supplier_id,
        quote_id,
        {
            'recommended_amount_minor': 12345,
            'reason_summary': '测试成交建议锁定',
        },
        [quote_item],
    )

    assert procurement_store.get_quote(quote_id)['is_locked'] == 1
    assert procurement_store.list_quotes(project_id)[0]['is_locked'] == 1
    with pytest.raises(ValueError, match='成交建议.*不能编辑'):
        procurement_store.update_quote(quote_id, {}, [])
    with pytest.raises(ValueError, match='成交建议.*不能删除'):
        procurement_store.delete_quote(quote_id)
