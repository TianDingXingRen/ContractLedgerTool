import os


def test_ledger_schema_module_keeps_compatibility_contract():
    import ledger_store
    from ledger_store import schema

    assert ledger_store.MIGRATIONS is schema.MIGRATIONS
    versions = [version for version, _forward, _rollback in schema.MIGRATIONS]
    assert versions == sorted(versions)
    assert versions[-1] >= 8


def test_init_db_uses_extracted_schema(tmp_path):
    import ledger_store

    old_data_dir = ledger_store.DATA_DIR
    old_db_path = ledger_store.DB_PATH
    old_backup_dir = ledger_store.BACKUP_DIR

    try:
        ledger_store.DATA_DIR = str(tmp_path)
        ledger_store.DB_PATH = str(tmp_path / 'contracts.db')
        ledger_store.BACKUP_DIR = str(tmp_path / 'backups')

        ledger_store.init_db()

        with ledger_store.get_conn() as conn:
            tables = {
                row['name']
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            indexes = {
                row['name']
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            schema_version = conn.execute(
                'SELECT MAX(version) AS version FROM schema_version'
            ).fetchone()['version']

        assert {'contracts', 'payment_plans', 'contract_history', 'schema_version'} <= tables
        assert 'idx_contracts_contract_no_unique' in indexes
        assert schema_version == ledger_store.MIGRATIONS[-1][0]
        assert os.path.isfile(ledger_store.DB_PATH)
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir
