"""Consistent SQLite connection scopes for all application stores."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def open_sqlite(
    database_path,
    *,
    timeout: float = 30,
    foreign_keys: bool = True,
    busy_timeout_ms: int = 30_000,
    query_only: bool = False,
) -> sqlite3.Connection:
    """Open one configured SQLite connection without owning its transaction."""
    connection = sqlite3.connect(os.fspath(database_path), timeout=timeout)
    connection.row_factory = sqlite3.Row
    if foreign_keys:
        connection.execute('PRAGMA foreign_keys = ON')
    if busy_timeout_ms:
        connection.execute(f'PRAGMA busy_timeout = {int(busy_timeout_ms)}')
    if query_only:
        connection.execute('PRAGMA query_only = ON')
    return connection


def begin_immediate(connection: sqlite3.Connection) -> None:
    """Reserve the SQLite write slot before a read/validate/write sequence.

    SQLite's default deferred transactions allow two writers to validate the
    same stale row before either update is issued.  Repositories that derive
    persisted fields from a preceding read use this helper so the read and the
    eventual write are serialized.  Existing caller-owned transactions keep
    their current boundary.
    """
    if not connection.in_transaction:
        connection.execute('BEGIN IMMEDIATE')


def _ensure_parent(database_path, directory=None) -> None:
    target = Path(directory) if directory is not None else Path(database_path).parent
    target.mkdir(parents=True, exist_ok=True)


@contextmanager
def transaction(
    database_path,
    *,
    directory=None,
    existing: sqlite3.Connection | None = None,
) -> Iterator[sqlite3.Connection]:
    """Yield a write connection and commit or roll back only when it is owned."""
    if existing is not None:
        yield existing
        return

    _ensure_parent(database_path, directory)
    connection = open_sqlite(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def query_snapshot(
    database_path,
    *,
    directory=None,
    existing: sqlite3.Connection | None = None,
) -> Iterator[sqlite3.Connection]:
    """Yield one query-only snapshot; callers manage any context-local reuse."""
    if existing is not None:
        yield existing
        return

    _ensure_parent(database_path, directory)
    connection = open_sqlite(database_path, query_only=True)
    connection.execute('BEGIN')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def checkpoint_wal(database_path) -> None:
    """Checkpoint and truncate a database WAL when the database exists."""
    path = Path(database_path)
    if not path.is_file():
        return
    connection = open_sqlite(path, foreign_keys=False, busy_timeout_ms=0)
    try:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        connection.close()
