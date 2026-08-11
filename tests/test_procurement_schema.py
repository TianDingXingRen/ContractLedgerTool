def test_procurement_schema_module_exposes_init_parts():
    from procurement_store import schema

    assert 'CREATE TABLE IF NOT EXISTS procurement_projects' in schema.PROCUREMENT_SCHEMA_SQL
    assert 'CREATE TABLE IF NOT EXISTS procurement_schema_version' in schema.PROCUREMENT_SCHEMA_SQL
    assert schema.SCHEMA_VERSION_INSERT_SQL.startswith('INSERT OR IGNORE')
    assert ('award_recommendations', 'is_split', 'INTEGER NOT NULL DEFAULT 0') in schema.V2_COLUMN_MIGRATIONS
    assert 'procurement_contract_refs' in schema.V3_CONTRACT_REFS_SQL
    assert (
        'project_suppliers', 'direct_support_experience', "TEXT DEFAULT ''"
    ) in schema.V5_SUPPLIER_COLUMN_MIGRATIONS
    assert schema.CURRENT_SCHEMA_VERSION == 6


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
            supplier_columns = {
                row['name']
                for row in conn.execute(
                    'PRAGMA table_info(project_suppliers)'
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
        assert {
            'direct_support_experience',
            'aerospace_support_experience',
            'qualifications',
        } <= supplier_columns
        assert schema_version == procurement_store.schema.CURRENT_SCHEMA_VERSION
        assert procurement_store.needs_migration() is False
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir


def test_procurement_v4_supplier_data_migrates_to_current(tmp_path):
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

        with ledger_store.get_conn() as conn:
            conn.executescript("""
                CREATE TABLE procurement_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_no TEXT NOT NULL UNIQUE,
                    project_name TEXT NOT NULL,
                    purchase_method TEXT NOT NULL DEFAULT 'competitive_negotiation',
                    demand_department TEXT DEFAULT '', owner TEXT DEFAULT '',
                    budget_minor INTEGER, target_price_minor INTEGER,
                    currency TEXT NOT NULL DEFAULT 'CNY', delivery_place TEXT DEFAULT '',
                    delivery_requirement TEXT DEFAULT '', payment_requirement TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft', remark TEXT DEFAULT '',
                    archived_at TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE project_suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    supplier_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    contact_person TEXT DEFAULT '', contact_phone TEXT DEFAULT '',
                    email TEXT DEFAULT '', invite_status TEXT NOT NULL DEFAULT 'pending',
                    quote_status TEXT NOT NULL DEFAULT 'pending', remark TEXT DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(project_id, normalized_name),
                    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
                );
                CREATE TABLE procurement_schema_version (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
                );
                INSERT INTO procurement_projects
                    (id, project_no, project_name, created_at, updated_at)
                    VALUES (1, 'CG-V4', '迁移测试项目', '2026-01-01', '2026-01-01');
                INSERT INTO project_suppliers
                    (project_id, supplier_name, normalized_name, remark, created_at, updated_at)
                    VALUES (1, '历史供应商', '历史供应商', '历史备注', '2026-01-01', '2026-01-01');
                INSERT INTO procurement_schema_version(version, applied_at)
                    VALUES (4, '2026-01-01');
            """)

        procurement_store.init_db()

        supplier = procurement_store.list_project_suppliers(1)[0]
        assert supplier['remark'] == '历史备注'
        assert supplier['direct_support_experience'] == ''
        assert supplier['aerospace_support_experience'] == ''
        assert supplier['qualifications'] == ''
        assert procurement_store.get_schema_version() == 6
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir


def test_procurement_v5_duplicate_file_versions_are_resequenced(tmp_path):
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
            conn.execute('DROP INDEX IF EXISTS uq_project_files_version')
            # Fresh v6 tables use a table-level auto-index; rebuild only the
            # legacy project_files shape to model a real v5 database.
            conn.execute('ALTER TABLE project_files RENAME TO project_files_v6')
            conn.executescript("""
                CREATE TABLE project_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    file_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    original_name TEXT DEFAULT '', sha256 TEXT DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, file_type, relative_path)
                );
                INSERT INTO procurement_projects
                    (id, project_no, project_name, purchase_method, currency,
                     status, created_at, updated_at)
                VALUES (1, 'V5-FILES', '文件迁移', 'competitive_negotiation',
                        'CNY', 'draft', '2026-01-01', '2026-01-01');
                INSERT INTO project_files
                    (project_id, file_type, relative_path, version, created_at)
                VALUES (1, 'inquiry', 'a.docx', 1, '2026-01-01'),
                       (1, 'inquiry', 'b.docx', 1, '2026-01-02');
                DROP TABLE project_files_v6;
                DELETE FROM procurement_schema_version;
                INSERT INTO procurement_schema_version(version, applied_at)
                VALUES (5, '2026-01-01');
            """)

        procurement_store.init_db()

        with ledger_store.get_conn() as conn:
            versions = [
                row['version']
                for row in conn.execute(
                    'SELECT version FROM project_files ORDER BY id'
                ).fetchall()
            ]
            index = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'index' "
                "AND name = 'uq_project_files_version'"
            ).fetchone()
        assert versions == [1, 2]
        assert index
        assert procurement_store.get_schema_version() == 6
    finally:
        ledger_store.close_connections()
        ledger_store.DATA_DIR = old_data_dir
        ledger_store.DB_PATH = old_db_path
        ledger_store.BACKUP_DIR = old_backup_dir
