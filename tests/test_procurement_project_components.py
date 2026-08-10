def _create_project(procurement_store):
    return procurement_store.create_project({
        'project_no': 'PC-001',
        'project_name': '项目子资源测试',
        'owner': '采购员',
    })


def test_project_item_and_supplier_components_match_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import project_components

    procurement_store.init_db()
    project_id = _create_project(procurement_store)

    item_id = procurement_store.add_project_item(project_id, {
        'item_name': '结构件A',
        'quantity_text': '10',
        'unit': '件',
    })
    bulk_ids = procurement_store.add_project_items_bulk(project_id, [
        {'item_name': '结构件B', 'quantity_text': '5', 'unit': '件'},
        {'item_name': '结构件C', 'quantity_text': '2', 'unit': '套'},
    ])
    assert procurement_store.list_project_items(project_id) == (
        project_components.list_project_items(ledger_store.get_conn, project_id)
    )
    assert [row['line_no'] for row in procurement_store.list_project_items(project_id)] == [1, 2, 3]

    procurement_store.update_project_item(project_id, item_id, {
        'item_name': '结构件A-更新',
        'quantity_text': '12',
        'unit': '件',
        'remark': '已更新',
    })
    assert procurement_store.get_project_item(item_id) == (
        project_components.get_project_item(
            ledger_store.get_conn, procurement_store._dict, item_id
        )
    )
    assert procurement_store.get_project_item(item_id)['item_name'] == '结构件A-更新'
    procurement_store.delete_project_item(project_id, bulk_ids[-1])
    assert len(procurement_store.list_project_items(project_id)) == 2

    supplier_id = procurement_store.add_project_supplier(project_id, {
        'supplier_name': ' 供应商A ',
        'contact_person': '张三',
        'direct_support_experience': '型号甲直接配套',
        'aerospace_support_experience': '有航空配套经验',
        'qualifications': '质量体系资质',
        'remark': '初始其他信息',
    })
    removable_supplier = procurement_store.add_project_supplier(project_id, {
        'supplier_name': '供应商B',
    })
    procurement_store.update_project_supplier(project_id, supplier_id, {
        'supplier_name': '供应商A-更新',
        'contact_person': '李四',
        'contact_phone': '13800000000',
        'direct_support_experience': '型号乙直接配套',
        'aerospace_support_experience': '航天结构件配套',
        'qualifications': '保密资质',
        'remark': '更新后的其他信息',
    })
    assert procurement_store.list_project_suppliers(project_id) == (
        project_components.list_project_suppliers(ledger_store.get_conn, project_id)
    )
    assert procurement_store.get_project_supplier(supplier_id) == (
        project_components.get_project_supplier(
            ledger_store.get_conn, procurement_store._dict, supplier_id
        )
    )
    saved_supplier = procurement_store.get_project_supplier(supplier_id)
    assert saved_supplier['normalized_name'] == '供应商a-更新'
    assert saved_supplier['direct_support_experience'] == '型号乙直接配套'
    assert saved_supplier['aerospace_support_experience'] == '航天结构件配套'
    assert saved_supplier['qualifications'] == '保密资质'
    assert saved_supplier['remark'] == '更新后的其他信息'
    procurement_store.delete_project_supplier(project_id, removable_supplier)
    assert len(procurement_store.list_project_suppliers(project_id)) == 1

    with ledger_store.get_conn() as conn:
        audit_actions = {
            row['action']
            for row in conn.execute(
                "SELECT action FROM procurement_audit_events WHERE entity_type IN ('project_item', 'project_supplier')"
            ).fetchall()
        }
    assert {'create', 'update', 'delete'} <= audit_actions


def test_project_file_components_match_public_wrappers(tmp_db):
    import ledger_store
    import procurement_store
    from procurement_store import project_components

    procurement_store.init_db()
    project_id = _create_project(procurement_store)

    first_id = procurement_store.register_project_file(
        project_id,
        'inquiry_letter',
        'procurement/PC-001/inquiry/a.docx',
        original_name='a.docx',
        sha256='hash-a',
        size_bytes=12,
    )
    duplicate_id = procurement_store.register_project_file(
        project_id,
        'inquiry_letter',
        'procurement/PC-001/inquiry/a.docx',
        original_name='a.docx',
        sha256='hash-a',
        size_bytes=12,
    )
    second_id = procurement_store.register_project_file(
        project_id,
        'inquiry_letter',
        'procurement/PC-001/inquiry/b.docx',
        original_name='b.docx',
        sha256='hash-b',
        size_bytes=34,
    )

    assert duplicate_id == first_id
    assert procurement_store.list_project_files(project_id) == (
        project_components.list_project_files(ledger_store.get_conn, project_id)
    )
    files = procurement_store.list_project_files(project_id)
    assert [row['id'] for row in files] == [second_id, first_id]
    assert [row['version'] for row in files] == [2, 1]
    assert procurement_store.get_project_file(first_id) == (
        project_components.get_project_file(
            ledger_store.get_conn, procurement_store._dict, first_id
        )
    )
