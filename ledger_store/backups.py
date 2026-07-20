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
        return []


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
    _validate_sqlite_backup(src)
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
    src = sqlite3.connect(db_path)
    try:
        src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        dst = sqlite3.connect(target_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    except Exception:
        get_logger().warning(
            'SQLite backup API failed; falling back to file copy',
            exc_info=True,
        )
        try:
            shutil.copy2(db_path, target_path)
        except Exception:
            get_logger().error('Database backup failed completely', exc_info=True)
            raise
    finally:
        src.close()


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
