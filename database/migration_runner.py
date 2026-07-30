"""Reusable primitives for SQLite schema versioning."""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from .connection_factory import open_sqlite


_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f'Invalid SQLite identifier: {value!r}')
    return value


def local_now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def row_to_dict(row):
    return dict(row) if row is not None else None


def ensure_column(connection, table_name: str, column_name: str, column_sql: str) -> bool:
    """Add a missing column and report whether the schema changed."""
    table = _identifier(table_name)
    column = _identifier(column_name)
    existing = {
        row['name'] if isinstance(row, sqlite3.Row) else row[1]
        for row in connection.execute(f'PRAGMA table_info({table})').fetchall()
    }
    if column in existing:
        return False
    connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} {column_sql}')
    return True


def read_schema_version(database_path, table_name: str) -> int:
    """Read a schema version table without creating or changing the database."""
    if not os.path.isfile(database_path) or os.path.getsize(database_path) == 0:
        return 0
    table = _identifier(table_name)
    connection = open_sqlite(
        database_path,
        foreign_keys=False,
        busy_timeout_ms=0,
    )
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if not exists:
            return 0
        row = connection.execute(
            f'SELECT COALESCE(MAX(version), 0) FROM {table}'
        ).fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        connection.close()


@dataclass(frozen=True)
class MigrationStep:
    version: int
    apply: Callable[[sqlite3.Connection], None]


def run_versioned_migrations(
    get_connection,
    *,
    current_version: int,
    steps: Iterable[MigrationStep],
    namespace: str,
    record_version: Callable[[sqlite3.Connection, int], None],
    on_error: Callable[[int, Exception], None] | None = None,
) -> int:
    """Run each pending migration in its own connection and savepoint."""
    prefix = _identifier(namespace)
    installed = int(current_version)
    for step in sorted(steps, key=lambda item: item.version):
        if step.version <= installed:
            continue
        with get_connection() as connection:
            savepoint = f'{prefix}_migration_v{int(step.version)}'
            connection.execute(f'SAVEPOINT {savepoint}')
            try:
                step.apply(connection)
                record_version(connection, step.version)
                connection.execute(f'RELEASE SAVEPOINT {savepoint}')
            except Exception as exc:
                connection.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                connection.execute(f'RELEASE SAVEPOINT {savepoint}')
                if on_error is not None:
                    on_error(step.version, exc)
                raise
        installed = step.version
    return installed
