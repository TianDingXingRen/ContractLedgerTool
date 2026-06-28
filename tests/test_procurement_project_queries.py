def test_procurement_project_queries_match_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import project_queries

    procurement_store.init_db()
    project_id = procurement_store.create_project({
        'project_no': 'PQ-001',
        'project_name': '采购项目A',
        'owner': '采购员A',
    })
    procurement_store.create_project({
        'project_no': 'PQ-002',
        'project_name': '其他项目',
        'owner': '采购员B',
    })
    procurement_store.add_project_item(project_id, {
        'item_name': '结构件',
        'quantity_text': '10',
        'unit': '件',
    })
    procurement_store.add_project_supplier(project_id, {
        'supplier_name': '供应商A',
    })
    procurement_store.transition_project_status(
        project_id, 'documents_ready', note='资料齐套'
    )

    assert procurement_store.get_project(project_id) == project_queries.get_project(
        ledger_store.get_conn, procurement_store._dict, project_id
    )
    project = procurement_store.get_project(project_id)
    assert project['item_count'] == 1
    assert project['supplier_count'] == 1
    assert project['quote_count'] == 0

    public_list = procurement_store.list_projects(
        status='documents_ready', q='项目A', page='0', per_page='500'
    )
    direct_list = project_queries.list_projects(
        ledger_store.get_conn,
        procurement_store._dict,
        status='documents_ready',
        q='项目A',
        page='0',
        per_page='500',
    )
    assert public_list == direct_list
    assert public_list['page'] == 1
    assert public_list['total'] == 1
    assert public_list['rows'][0]['id'] == project_id

    public_events = procurement_store.list_project_audit_events(
        project_id, actions=['status_change']
    )
    direct_events = project_queries.list_project_audit_events(
        ledger_store.get_conn, project_id, actions=['status_change']
    )
    assert public_events == direct_events
    assert public_events[0]['before'] == {'status': 'draft'}
    assert public_events[0]['after'] == {'status': 'documents_ready'}
    assert public_events[0]['note'] == '资料齐套'
