import os
import sqlite3


def test_ledger_schema_module_keeps_compatibility_contract():
    import ledger_store
    from ledger_store import schema

    assert ledger_store.MIGRATIONS is schema.MIGRATIONS
    versions = [version for version, _forward, _rollback in schema.MIGRATIONS]
    assert versions == sorted(versions)
    assert versions[-1] == schema.CURRENT_SCHEMA_VERSION


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
            contract_columns = {
                row['name']
                for row in conn.execute('PRAGMA table_info(contracts)').fetchall()
            }
            payment_columns = {
                row['name']
                for row in conn.execute('PRAGMA table_info(payment_plans)').fetchall()
            }

        assert {
            'contracts',
            'payment_plans',
            'payment_rules',
            'payment_trigger_events',
            'contract_history',
            'contract_generation_jobs',
            'schema_version',
        } <= tables
        assert 'idx_contracts_contract_no_unique' in indexes
        assert 'idx_generation_jobs_active_output' in indexes
        assert 'subsystem_name' in contract_columns
        assert 'coverage_not_applicable' in contract_columns
        assert 'subsystem_name' in payment_columns
        assert schema_version == ledger_store.MIGRATIONS[-1][0]
        assert ledger_store.needs_migration() is False
        assert os.path.isfile(ledger_store.DB_PATH)
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir


def test_init_db_repairs_legacy_contract_columns_before_indexes(tmp_path):
    import ledger_store

    old_data_dir = ledger_store.DATA_DIR
    old_db_path = ledger_store.DB_PATH
    old_backup_dir = ledger_store.BACKUP_DIR

    try:
        ledger_store.DATA_DIR = str(tmp_path)
        ledger_store.DB_PATH = str(tmp_path / 'contracts.db')
        ledger_store.BACKUP_DIR = str(tmp_path / 'backups')

        conn = sqlite3.connect(ledger_store.DB_PATH)
        conn.executescript(
            """
            CREATE TABLE contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_no TEXT,
                title TEXT NOT NULL,
                counterparty TEXT,
                amount REAL,
                sign_date TEXT,
                owner TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                template_name TEXT,
                docx_path TEXT,
                values_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_version (version, applied_at)
            VALUES (8, '2026-01-01 00:00:00');
            """
        )
        conn.commit()
        conn.close()

        ledger_store.init_db()

        with ledger_store.get_conn() as conn:
            columns = {
                row['name']
                for row in conn.execute('PRAGMA table_info(contracts)').fetchall()
            }
            indexes = {
                row['name']
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }

        assert {
            'deleted_at',
            'expiry_date',
            'project_name',
            'subsystem_name',
            'coverage_not_applicable',
            'coverage_start',
            'coverage_end',
        } <= columns
        assert 'idx_contracts_expiry' in indexes
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir
