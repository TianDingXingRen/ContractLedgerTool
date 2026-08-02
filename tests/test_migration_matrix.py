import sqlite3
from contextlib import closing
from pathlib import Path

import ledger_store
from ledger_store.schema import (
    CURRENT_SCHEMA_VERSION,
    MIGRATION_BACKFILLS,
    MIGRATIONS,
    SCHEMA_VERSION_SQL,
)


_V1_SCHEMA = """
CREATE TABLE contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT, title TEXT NOT NULL, counterparty TEXT, amount REAL,
    sign_date TEXT, owner TEXT, status TEXT NOT NULL DEFAULT 'draft',
    template_name TEXT, docx_path TEXT, values_json TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE payment_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL,
    phase_name TEXT, payment_type TEXT NOT NULL DEFAULT 'conditional',
    trigger_event TEXT, trigger_days INTEGER, expected_trigger_date TEXT,
    due_date TEXT, ratio REAL, due_amount REAL, paid_amount REAL NOT NULL DEFAULT 0,
    paid_date TEXT, condition_text TEXT, source_text TEXT,
    confidence TEXT NOT NULL DEFAULT 'low', confirm_status TEXT NOT NULL DEFAULT 'pending',
    payment_status TEXT NOT NULL DEFAULT 'unpaid', remark TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE contract_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL,
    field TEXT NOT NULL, old_value TEXT, new_value TEXT, changed_at TEXT NOT NULL
);
INSERT INTO contracts (
    contract_no, title, amount, docx_path, created_at, updated_at
) VALUES ('MATRIX-001', 'Migration matrix', 123.45, 'output/matrix.docx', '2026-01-01', '2026-01-01');
INSERT INTO payment_plans (
    contract_id, phase_name, due_amount, paid_amount, created_at, updated_at
) VALUES (1, '首付款', 12.34, 1.23, '2026-01-01', '2026-01-01');
"""


def _create_database_at_version(path, target_version):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(_V1_SCHEMA)
        connection.executescript(SCHEMA_VERSION_SQL)
        connection.execute(
            'INSERT INTO schema_version(version, applied_at) VALUES (1, ?)',
            ('2026-01-01',),
        )
        for version, forward_sql, _rollback_sql in MIGRATIONS:
            if version > target_version:
                break
            if version == 17:
                existing = {
                    row[1]
                    for row in connection.execute('PRAGMA table_info(contracts)')
                }
                for column, definition in {
                    'record_origin': "TEXT NOT NULL DEFAULT 'generated'",
                    'original_filename': "TEXT DEFAULT ''",
                    'source_sha256': "TEXT DEFAULT ''",
                }.items():
                    if column not in existing:
                        connection.execute(
                            f'ALTER TABLE contracts ADD COLUMN {column} {definition}'
                        )
            connection.executescript(forward_sql)
            if version in MIGRATION_BACKFILLS:
                connection.executescript(MIGRATION_BACKFILLS[version])
            connection.execute(
                'INSERT INTO schema_version(version, applied_at) VALUES (?, ?)',
                (version, '2026-01-01'),
            )
        connection.commit()


def test_every_historical_ledger_version_upgrades_to_current(tmp_path, monkeypatch):
    for starting_version in range(1, CURRENT_SCHEMA_VERSION):
        runtime_dir = tmp_path / f'v{starting_version}'
        runtime_dir.mkdir()
        database = runtime_dir / 'contracts.db'
        _create_database_at_version(database, starting_version)
        monkeypatch.setattr(ledger_store, 'DB_PATH', str(database))
        monkeypatch.setattr(ledger_store, 'DATA_DIR', str(runtime_dir))

        ledger_store.run_migrations()

        assert ledger_store.get_schema_version() == CURRENT_SCHEMA_VERSION
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            contract = connection.execute(
                'SELECT amount_minor, record_origin, original_filename, source_sha256 '
                'FROM contracts WHERE contract_no = ?', ('MATRIX-001',)
            ).fetchone()
            payment = connection.execute(
                'SELECT due_amount_minor, paid_amount_minor, contract_serial_id '
                'FROM payment_plans WHERE id = 1'
            ).fetchone()
            serial_table = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'contract_serials'"
            ).fetchone()
        assert contract == (12_345, 'generated', '', '')
        assert payment == (1_234, 123, None)
        assert serial_table == ('contract_serials',)


def test_restore_supported_historical_ledger_only_backup(tmp_db):
    backup_path = Path(ledger_store.BACKUP_DIR) / 'legacy-ledger-only.db'
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    _create_database_at_version(backup_path, 1)

    ledger_store.restore_backup(backup_path.name)

    assert ledger_store.get_schema_version() == CURRENT_SCHEMA_VERSION
    with closing(sqlite3.connect(ledger_store.DB_PATH)) as connection:
        contract = connection.execute(
            'SELECT title FROM contracts WHERE contract_no = ?',
            ('MATRIX-001',),
        ).fetchone()
        procurement_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('procurement_projects', "
                "'procurement_schema_version')"
            )
        }

    assert contract == ('Migration matrix',)
    assert procurement_tables == {
        'procurement_projects',
        'procurement_schema_version',
    }
