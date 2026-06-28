def test_procurement_schema_module_exposes_init_parts():
    from procurement_store import schema

    assert 'CREATE TABLE IF NOT EXISTS procurement_projects' in schema.PROCUREMENT_SCHEMA_SQL
    assert 'CREATE TABLE IF NOT EXISTS procurement_schema_version' in schema.PROCUREMENT_SCHEMA_SQL
    assert schema.SCHEMA_VERSION_INSERT_SQL.startswith('INSERT OR IGNORE')
    assert ('award_recommendations', 'is_split', 'INTEGER NOT NULL DEFAULT 0') in schema.V2_COLUMN_MIGRATIONS
    assert 'procurement_contract_refs' in schema.V3_CONTRACT_REFS_SQL


def test_procurement_init_db_uses_extracted_schema(tmp_path):
    import ledger_store
    import procurement_store

    old_data_dir = ledger_store.DATA_DIR
    old_db_path = ledger_store.DB_PATH
    old_backup_dir = ledger_store.BACKUP_DIR

    try:
        ledger_store.DATA_DIR = str(tmp_path)
        ledger_store.DB_PATH = str(tmp_path / 'contracts.db')
        ledger_store.BACKUP_DIR = str(tmp_path / 'backups')

        ledger_store.init_db()
        procurement_store.init_db()

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
            award_columns = {
                row['name']
                for row in conn.execute(
                    'PRAGMA table_info(award_recommendations)'
                ).fetchall()
            }
            item_columns = {
                row['name']
                for row in conn.execute(
                    'PRAGMA table_info(award_recommendation_items)'
                ).fetchall()
            }
            schema_version = conn.execute(
                'SELECT MAX(version) AS version FROM procurement_schema_version'
            ).fetchone()['version']

        assert {
            'procurement_projects',
            'project_items',
            'project_suppliers',
            'supplier_quotes',
            'procurement_contract_refs',
            'procurement_schema_version',
        } <= tables
        assert 'idx_procurement_project_status' in indexes
        assert 'idx_procurement_contract_refs_project' in indexes
        assert {'is_split', 'supplier_summary'} <= award_columns
        assert {'supplier_id', 'quote_id'} <= item_columns
        assert schema_version == 3
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir
