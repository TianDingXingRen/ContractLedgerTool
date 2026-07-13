import sqlite3


def _create_legacy_database(path):
    conn = sqlite3.connect(path)
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
        CREATE TABLE payment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            phase_name TEXT,
            payment_type TEXT NOT NULL DEFAULT 'conditional',
            trigger_event TEXT,
            trigger_days INTEGER,
            expected_trigger_date TEXT,
            due_date TEXT,
            ratio REAL,
            due_amount REAL,
            paid_amount REAL NOT NULL DEFAULT 0,
            paid_date TEXT,
            condition_text TEXT,
            source_text TEXT,
            confidence TEXT NOT NULL DEFAULT 'low',
            confirm_status TEXT NOT NULL DEFAULT 'pending',
            payment_status TEXT NOT NULL DEFAULT 'unpaid',
            remark TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE contract_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            field TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TEXT NOT NULL
        );
        INSERT INTO contracts (
            contract_no, title, counterparty, amount, sign_date, owner, status,
            template_name, docx_path, values_json, created_at, updated_at
        ) VALUES (
            'LEGACY-001', 'Legacy contract', 'Old supplier', 12345.67,
            '2025-01-01', 'Owner', 'active', 'legacy-template',
            'output/legacy.docx', '{"legacy": true}',
            '2025-01-01 10:00:00', '2025-01-01 10:00:00'
        );
        """
    )
    conn.commit()
    conn.close()


def test_app_upgrade_backs_up_legacy_database_before_migration(tmp_path):
    import app as app_module

    runtime_dir = tmp_path / 'runtime'
    data_dir = runtime_dir / 'data'
    data_dir.mkdir(parents=True)
    database = data_dir / 'contracts.db'
    _create_legacy_database(database)

    original_base = app_module.BASE_DIR
    original_resources = app_module.RESOURCE_DIR
    try:
        app_module.create_app(
            runtime_base_dir=runtime_dir,
            resource_dir=original_resources,
            run_maintenance=False,
            testing=True,
        )

        backups = sorted((data_dir / 'backups').glob('*before_upgrade.db'))
        assert len(backups) == 1

        with sqlite3.connect(backups[0]) as conn:
            backup_row = conn.execute(
                'SELECT contract_no, title, values_json FROM contracts'
            ).fetchone()
            backup_columns = {
                row[1] for row in conn.execute('PRAGMA table_info(contracts)')
            }

        with sqlite3.connect(database) as conn:
            upgraded_row = conn.execute(
                'SELECT contract_no, title, values_json FROM contracts'
            ).fetchone()
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            migrated_columns = {
                row[1] for row in conn.execute('PRAGMA table_info(contracts)')
            }

        assert backup_row == ('LEGACY-001', 'Legacy contract', '{"legacy": true}')
        assert 'deleted_at' not in backup_columns
        assert upgraded_row == backup_row
        assert integrity == 'ok'
        assert {'deleted_at', 'expiry_date', 'project_name'} <= migrated_columns
    finally:
        app_module.reset_runtime()
        app_module.configure_runtime_paths(original_base, original_resources)


def test_packaged_asset_upgrade_never_overwrites_user_files(tmp_path):
    from runtime.maintenance import seed_packaged_assets
    from runtime.paths import RuntimePaths

    resource_dir = tmp_path / 'resources'
    runtime_dir = tmp_path / 'runtime'
    paths = RuntimePaths.create(runtime_dir, resource_dir)
    paths.ensure_writable_dirs()

    (resource_dir / 'templates').mkdir(parents=True)
    (resource_dir / 'uploads').mkdir(parents=True)
    (resource_dir / 'version.txt').write_text('1.0.0', encoding='utf-8')
    packaged_template = resource_dir / 'templates' / 'default.contract-template'
    packaged_upload = resource_dir / 'uploads' / 'default.docx'
    packaged_template.write_text('packaged-v1', encoding='utf-8')
    packaged_upload.write_text('packaged-doc-v1', encoding='utf-8')

    seed_packaged_assets(paths)
    user_template = paths.templates_dir / packaged_template.name
    user_upload = paths.uploads_dir / packaged_upload.name
    user_template.write_text('user-template', encoding='utf-8')
    user_upload.write_text('user-document', encoding='utf-8')

    (resource_dir / 'version.txt').write_text('2.0.0', encoding='utf-8')
    packaged_template.write_text('packaged-v2', encoding='utf-8')
    packaged_upload.write_text('packaged-doc-v2', encoding='utf-8')
    seed_packaged_assets(paths)

    assert user_template.read_text(encoding='utf-8') == 'user-template'
    assert user_upload.read_text(encoding='utf-8') == 'user-document'
    assert (paths.base_dir / '.installed_version').read_text(encoding='utf-8') == '2.0.0'
