"""Shared SQLite infrastructure for application stores."""

from .connection_factory import (
    checkpoint_wal,
    open_sqlite,
    query_snapshot,
    transaction,
)
from .migration_runner import (
    MigrationStep,
    ensure_column,
    local_now,
    read_schema_version,
    row_to_dict,
    run_versioned_migrations,
)

__all__ = [
    'MigrationStep',
    'checkpoint_wal',
    'ensure_column',
    'local_now',
    'open_sqlite',
    'query_snapshot',
    'read_schema_version',
    'row_to_dict',
    'run_versioned_migrations',
    'transaction',
]
