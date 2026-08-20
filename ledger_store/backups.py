"""Backup and restore helpers for the ledger database."""

import os
import re
import shutil
import sqlite3
import uuid
from datetime import date, datetime

from utils.logger import get_logger
from utils.security import path_within


_SCHEDULED_BACKUP_RE = re.compile(r'^contracts_\d{4}-\d{2}-\d{2}\.db$')
_REQUIRED_APPLICATION_TABLES = {
    'contracts',
    'payment_plans',
}
_REQUIRED_APPLICATION_COLUMNS = {
    'contracts': {'id', 'title', 'created_at', 'updated_at'},
    'payment_plans': {
        'id', 'contract_id', 'due_amount', 'created_at', 'updated_at',
    },
}
_PROCUREMENT_IDENTITY_TABLES = {
    'procurement_projects',
    'procurement_schema_version',
}


def _is_scheduled_backup(filename):
    return bool(_SCHEDULED_BACKUP_RE.fullmatch(filename or ''))


def get_all_docx_paths(get_conn, db_path):
    if not os.path.isfile(db_path):
        return []
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT docx_path FROM contracts WHERE docx_path IS NOT NULL AND docx_path != ''"
            ).fetchall()
        return [row[0] for row in rows]
    except Exception:
        get_logger().warning('Unable to query contract docx paths', exc_info=True)
        # Callers use this list as a deletion protection set.  Returning an
        # empty list on query failure turns an unavailable ledger into "no
        # referenced documents" and can make maintenance delete live files.
        raise


def check_db_integrity(get_conn, db_path, quick=True):
    if not os.path.isfile(db_path):
        return False
    pragma = 'PRAGMA quick_check' if quick else 'PRAGMA integrity_check'
    try:
        with get_conn() as conn:
            row = conn.execute(pragma).fetchone()
            return row is not None and row[0] == 'ok'
    except Exception:
        get_logger().warning('Database integrity check failed: %s', pragma, exc_info=True)
        return False


def backup_database(get_conn, db_path, backup_dir, max_backups=7):
    if not os.path.exists(db_path):
        return None
    if not check_db_integrity(get_conn, db_path, quick=False):
        get_logger().warning('Database integrity check failed; skip scheduled backup')
        return None
    os.makedirs(backup_dir, exist_ok=True)
    today = date.today().strftime('%Y-%m-%d')
    target_path = os.path.join(backup_dir, f'contracts_{today}.db')
    if not os.path.exists(target_path):
        _copy_database(db_path, target_path)
    rows = sorted(
        [name for name in os.listdir(backup_dir) if _is_scheduled_backup(name)],
        reverse=True,
    )
    for old in rows[max_backups:]:
        os.remove(os.path.join(backup_dir, old))
    return target_path


def list_backups(backup_dir):
    if not os.path.isdir(backup_dir):
        return []
    rows = []
    for filename in os.listdir(backup_dir):
        if not filename.endswith('.db'):
            continue
        path = os.path.abspath(os.path.join(backup_dir, filename))
        if not path_within(backup_dir, path):
            continue
        stat = os.stat(path)
        rows.append({
            'filename': filename,
            'path': path,
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        })
    rows.sort(key=lambda item: (item['mtime'], item['filename']), reverse=True)
    return rows


def create_backup(db_path, backup_dir, label='manual'):
    if not os.path.exists(db_path):
        raise FileNotFoundError('Database file does not exist')
    os.makedirs(backup_dir, exist_ok=True)
    safe_label = ''.join(
        ch if ch.isalnum() or ch in ('-', '_') else '_'
        for ch in str(label or 'manual')
    )[:32]
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    target_path = os.path.abspath(os.path.join(
        backup_dir, f'contracts_{stamp}_{safe_label}.db'
    ))
    if not path_within(backup_dir, target_path):
        raise ValueError('Invalid backup path')
    _copy_database(db_path, target_path)
    try:
        _validate_sqlite_backup(target_path)
    except Exception:
        try:
            os.remove(target_path)
        except OSError:
            get_logger().warning(
                '无效备份校验失败后无法删除文件: %s', target_path, exc_info=True,
            )
        raise
    return {
        'filename': os.path.basename(target_path),
        'path': target_path,
        'size': os.path.getsize(target_path),
    }


def backup_path(backup_dir, filename):
    name = os.path.basename(filename or '')
    if not name.endswith('.db'):
        raise FileNotFoundError('Backup file does not exist')
    path = os.path.abspath(os.path.join(backup_dir, name))
    if not path_within(backup_dir, path) or not os.path.isfile(path):
        raise FileNotFoundError('Backup file does not exist')
    return path


def restore_backup(db_path, data_dir, backup_dir, filename, create_backup_func):
    src = backup_path(backup_dir, filename)
    _validate_application_backup(src)
    rollback = None
    if os.path.exists(db_path):
        rollback = create_backup_func('before_restore')
    replace_database(db_path, data_dir, src)
    return db_path, rollback


def replace_database(db_path, data_dir, source_path):
    """Validate and atomically replace a SQLite database file."""
    os.makedirs(data_dir, exist_ok=True)
    temp_path = os.path.join(data_dir, f'.restore_{uuid.uuid4().hex}.db')
    try:
        shutil.copy2(source_path, temp_path)
        _validate_sqlite_backup(temp_path)
        os.replace(temp_path, db_path)
        for suffix in ('-wal', '-shm'):
            sidecar = db_path + suffix
            try:
                os.remove(sidecar)
            except FileNotFoundError:
                get_logger().debug('SQLite sidecar already absent: %s', sidecar)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            get_logger().debug('Restore staging database already absent: %s', temp_path)


def _copy_database(db_path, target_path):
    temp_target = f'{target_path}.tmp-{uuid.uuid4().hex}'
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(temp_target)
        try:
            src.backup(dst)
        finally:
            dst.close()
        _validate_sqlite_backup(temp_target)
        os.replace(temp_target, target_path)
    finally:
        src.close()
        try:
            os.remove(temp_target)
        except FileNotFoundError:
            get_logger().debug('Backup staging file already absent: %s', temp_target)


def _validate_sqlite_backup(path):
    conn = None
    try:
        conn = sqlite3.connect(path)
        row = conn.execute('PRAGMA quick_check').fetchone()
        if row is None or row[0] != 'ok':
            detail = row[0] if row else 'unreadable'
            raise ValueError(f'Backup validation failed: {detail}')
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'Backup file is not a valid SQLite database: {exc}') from exc
    finally:
        if conn:
            conn.close()


def _validate_application_backup(path):
    """Reject valid SQLite files that are not compatible application backups."""
    _validate_sqlite_backup(path)
    conn = None
    try:
        conn = sqlite3.connect(path)
        conn.execute('PRAGMA query_only = ON')
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_APPLICATION_TABLES - tables)
        if missing:
            raise ValueError(
                f'备份数据库缺少应用表: {", ".join(missing)}'
            )
        for table, required_columns in _REQUIRED_APPLICATION_COLUMNS.items():
            columns = {
                str(row[1])
                for row in conn.execute(f'PRAGMA table_info({table})').fetchall()
            }
            missing_columns = sorted(required_columns - columns)
            if missing_columns:
                raise ValueError(
                    f'备份数据库应用表 {table} 缺少字段: '
                    f'{", ".join(missing_columns)}'
                )

        procurement_identity = tables & _PROCUREMENT_IDENTITY_TABLES
        if procurement_identity and procurement_identity != _PROCUREMENT_IDENTITY_TABLES:
            missing = sorted(_PROCUREMENT_IDENTITY_TABLES - tables)
            raise ValueError(
                f'备份数据库缺少采购应用表: {", ".join(missing)}'
            )

        ledger_version = None
        if 'schema_version' in tables:
            ledger_row = conn.execute(
                'SELECT MAX(version) FROM schema_version'
            ).fetchone()
            ledger_version = int(ledger_row[0] or 0) if ledger_row else 0
        procurement_version = None
        if procurement_identity:
            procurement_row = conn.execute(
                'SELECT MAX(version) FROM procurement_schema_version'
            ).fetchone()
            procurement_version = (
                int(procurement_row[0] or 0) if procurement_row else 0
            )

        from .schema import CURRENT_SCHEMA_VERSION as max_ledger_version
        from procurement_store.schema import (
            CURRENT_SCHEMA_VERSION as max_procurement_version,
        )

        if (ledger_version is not None and ledger_version < 1) or (
            procurement_version is not None and procurement_version < 1
        ):
            raise ValueError('备份数据库缺少有效的架构版本记录')
        if ledger_version is not None and ledger_version > max_ledger_version:
            raise ValueError(
                f'备份数据库版本过新: {ledger_version} > {max_ledger_version}'
            )
        if (
            procurement_version is not None
            and procurement_version > max_procurement_version
        ):
            raise ValueError(
                '备份采购数据库版本过新: '
                f'{procurement_version} > {max_procurement_version}'
            )
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'无法验证备份数据库架构: {exc}') from exc
    finally:
        if conn:
            conn.close()
