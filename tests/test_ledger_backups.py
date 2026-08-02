import os
import shutil
import sqlite3
from contextlib import closing
from datetime import date, timedelta

import pytest


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


def test_contract_document_path_rebases_after_runtime_move(tmp_path, monkeypatch):
    import ledger_store

    runtime_a = tmp_path / 'runtime_a'
    runtime_b = tmp_path / 'runtime_b'
    (runtime_a / 'data').mkdir(parents=True)
    (runtime_a / 'output').mkdir(parents=True)
    source_docx = runtime_a / 'output' / 'generated.docx'
    source_docx.write_bytes(b'docx')

    monkeypatch.setattr(ledger_store, 'DATA_DIR', str(runtime_a / 'data'))
    monkeypatch.setattr(ledger_store, 'DB_PATH', str(runtime_a / 'data' / 'contracts.db'))
    monkeypatch.setattr(ledger_store, 'BACKUP_DIR', str(runtime_a / 'data' / 'backups'))
    ledger_store.init_db()
    contract_id = ledger_store.create_contract({'title': 'Portable'}, {}, str(source_docx))

    with sqlite3.connect(ledger_store.DB_PATH) as conn:
        stored_path = conn.execute(
            'SELECT docx_path FROM contracts WHERE id = ?', (contract_id,)
        ).fetchone()[0]
    assert stored_path == 'output/generated.docx'

    shutil.copytree(runtime_a, runtime_b)
    monkeypatch.setattr(ledger_store, 'DATA_DIR', str(runtime_b / 'data'))
    monkeypatch.setattr(ledger_store, 'DB_PATH', str(runtime_b / 'data' / 'contracts.db'))
    monkeypatch.setattr(ledger_store, 'BACKUP_DIR', str(runtime_b / 'data' / 'backups'))
    ledger_store.init_db()

    moved = ledger_store.get_contract(contract_id)
    assert moved['docx_path'] == str(runtime_b / 'output' / 'generated.docx')
    assert os.path.isfile(moved['docx_path'])


def test_scheduled_retention_never_removes_safety_or_manual_backups(tmp_db):
    import ledger_store

    ledger_store.create_contract({'title': 'Retention'}, {}, '')
    protected = [
        ledger_store.create_backup('manual')['path'],
        ledger_store.create_backup('before_upgrade')['path'],
        ledger_store.create_backup('before_restore')['path'],
    ]
    backup_dir = ledger_store.BACKUP_DIR
    for offset in range(12):
        day = date(2026, 1, 1) + timedelta(days=offset)
        path = os.path.join(backup_dir, f'contracts_{day:%Y-%m-%d}.db')
        shutil.copy2(ledger_store.DB_PATH, path)

    ledger_store.backup_database(max_backups=7)

    assert all(os.path.isfile(path) for path in protected)
    scheduled = [
        name for name in os.listdir(backup_dir)
        if name.startswith('contracts_2026-') and name.endswith('.db')
    ]
    assert len(scheduled) == 7


def test_restore_rejects_sqlite_without_application_schema(tmp_db):
    import ledger_store

    contract_id = ledger_store.create_contract({'title': 'Keep Me'}, {}, '')
    invalid_path = os.path.join(ledger_store.BACKUP_DIR, 'invalid-schema.db')
    os.makedirs(ledger_store.BACKUP_DIR, exist_ok=True)
    with closing(sqlite3.connect(invalid_path)) as connection:
        connection.execute('CREATE TABLE notes (value TEXT)')
        connection.execute("INSERT INTO notes VALUES ('not an app backup')")
        connection.commit()

    with pytest.raises(ValueError, match='备份数据库缺少应用表'):
        ledger_store.restore_backup(os.path.basename(invalid_path))

    assert ledger_store.get_contract(contract_id)['title'] == 'Keep Me'


def test_restore_rejects_backup_from_newer_ledger_schema(tmp_db):
    import ledger_store

    contract_id = ledger_store.create_contract({'title': 'Current Data'}, {}, '')
    backup = ledger_store.create_backup('future_schema')
    with closing(sqlite3.connect(backup['path'])) as connection:
        connection.execute(
            'INSERT INTO schema_version (version, applied_at) VALUES (?, ?)',
            (ledger_store.CURRENT_SCHEMA_VERSION + 1, '2099-01-01 00:00:00'),
        )
        connection.commit()

    with pytest.raises(ValueError, match='备份数据库版本过新'):
        ledger_store.restore_backup(backup['filename'])

    assert ledger_store.get_contract(contract_id)['title'] == 'Current Data'
