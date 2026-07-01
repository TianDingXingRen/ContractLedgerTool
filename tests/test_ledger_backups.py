import os


def test_ledger_backup_wrappers_delegate_to_split_module(tmp_db):
    import ledger_store

    docx_path = os.path.join(tmp_db, 'contract.docx')
    contract_id = ledger_store.create_contract({'title': 'Backup Test'}, {}, docx_path)

    assert contract_id
    assert ledger_store.get_all_docx_paths() == [docx_path]
    assert ledger_store._check_db_integrity(quick=True)

    backup = ledger_store.create_backup()
    assert backup['filename'].endswith('.db')
    assert os.path.isfile(backup['path'])
    assert ledger_store.backup_path(backup['filename']) == backup['path']
    assert ledger_store.list_backups()[0]['filename'] == backup['filename']

    scheduled = ledger_store.backup_database(max_backups=7)
    assert scheduled is not None
    assert os.path.isfile(scheduled)
