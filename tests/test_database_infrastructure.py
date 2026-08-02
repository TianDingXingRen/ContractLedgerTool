import sqlite3

import pytest

from database.connection_factory import transaction
from database.migration_runner import (
    MigrationStep,
    ensure_column,
    read_schema_version,
    run_versioned_migrations,
)


def test_transaction_factory_commits_and_rolls_back(tmp_path):
    database = tmp_path / 'store.db'
    with transaction(database) as connection:
        connection.execute('CREATE TABLE records (value TEXT NOT NULL)')
        connection.execute('INSERT INTO records(value) VALUES (?)', ('kept',))

    with pytest.raises(RuntimeError):
        with transaction(database) as connection:
            connection.execute('INSERT INTO records(value) VALUES (?)', ('rolled-back',))
            raise RuntimeError('stop')

    with sqlite3.connect(database) as connection:
        values = [
            row[0]
            for row in connection.execute('SELECT value FROM records ORDER BY rowid')
        ]
    assert values == ['kept']


def test_migration_runner_commits_versions_independently(tmp_path):
    database = tmp_path / 'store.db'
    with transaction(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE records (value TEXT NOT NULL);
            """
        )

    def get_connection():
        return transaction(database)

    def record_version(connection, version):
        connection.execute(
            'INSERT INTO schema_version(version, applied_at) VALUES (?, ?)',
            (version, '2026-07-27 00:00:00'),
        )

    def fail_second(connection):
        connection.execute('INSERT INTO records(value) VALUES (?)', ('rolled-back',))
        raise RuntimeError('migration failed')

    with pytest.raises(RuntimeError, match='migration failed'):
        run_versioned_migrations(
            get_connection,
            current_version=0,
            steps=(
                MigrationStep(
                    1,
                    lambda connection: connection.execute(
                        'INSERT INTO records(value) VALUES (?)',
                        ('kept',),
                    ),
                ),
                MigrationStep(2, fail_second),
            ),
            namespace='test_store',
            record_version=record_version,
        )

    assert read_schema_version(database, 'schema_version') == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT value FROM records').fetchall() == [('kept',)]


def test_ensure_column_is_idempotent(tmp_path):
    database = tmp_path / 'store.db'
    with transaction(database) as connection:
        connection.execute('CREATE TABLE records (id INTEGER PRIMARY KEY)')
        assert ensure_column(connection, 'records', 'note', "TEXT DEFAULT ''") is True
        assert ensure_column(connection, 'records', 'note', "TEXT DEFAULT ''") is False
