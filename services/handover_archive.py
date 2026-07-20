"""Safe archive and SQLite primitives for handover packages."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import PurePosixPath

from utils import helpers


def safe_label(value, default='handover'):
    label = helpers.safe_filename_part(str(value or '').strip(), default)[:36]
    return label or default


def archive_name(*parts):
    return '/'.join(str(part).strip('/\\') for part in parts if str(part).strip('/\\'))


def normalize_archive_name(name):
    raw = str(name or '')
    if not raw or '\\' in raw:
        raise ValueError('数据包内文件路径无效')
    path = PurePosixPath(raw.strip('/'))
    if path.is_absolute() or not path.parts:
        raise ValueError('数据包内文件路径无效')
    if any(part in {'', '.', '..'} for part in path.parts):
        raise ValueError('数据包内文件路径无效')
    if ':' in path.parts[0]:
        raise ValueError('数据包内文件路径无效')
    return str(path)


def member_allowed(name, roots, manifest_name):
    if name == manifest_name:
        return True
    return any(name == root or name.startswith(root + '/') for root in roots)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_member(zf, name):
    digest = hashlib.sha256()
    with zf.open(name) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def copy_database(db_path, target_path):
    if not os.path.isfile(db_path):
        raise FileNotFoundError('数据库文件不存在')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    source = sqlite3.connect(db_path)
    try:
        source.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        destination = sqlite3.connect(target_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()


def validate_sqlite_file(path):
    connection = None
    try:
        connection = sqlite3.connect(path)
        row = connection.execute('PRAGMA quick_check').fetchone()
        if row is None or row[0] != 'ok':
            detail = row[0] if row else 'unreadable'
            raise ValueError(f'数据库校验失败: {detail}')
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'数据包内数据库无效: {exc}') from exc
    finally:
        if connection:
            connection.close()


def add_file(zf, source_path, archive_path, records):
    if not os.path.isfile(source_path) or os.path.islink(source_path):
        return False
    archive_path = normalize_archive_name(archive_path)
    zf.write(source_path, archive_path)
    file_stat = os.stat(source_path)
    records.append({
        'path': archive_path,
        'size': file_stat.st_size,
        'sha256': sha256_file(source_path),
    })
    return True


def add_directory(zf, source_dir, archive_root, records):
    archive_root = normalize_archive_name(archive_root)
    root_info = {'path': archive_root, 'kind': 'dir', 'present': os.path.isdir(source_dir)}
    if not root_info['present']:
        return root_info
    zf.writestr(archive_root + '/', b'')
    for current, dirs, files in os.walk(source_dir):
        dirs[:] = [
            dirname for dirname in dirs
            if not os.path.islink(os.path.join(current, dirname))
        ]
        rel_dir = os.path.relpath(current, source_dir)
        if rel_dir != '.':
            zf.writestr(archive_name(archive_root, rel_dir.replace(os.sep, '/')) + '/', b'')
        for filename in files:
            source_path = os.path.join(current, filename)
            if os.path.islink(source_path):
                continue
            rel_path = os.path.relpath(source_path, source_dir).replace(os.sep, '/')
            add_file(zf, source_path, archive_name(archive_root, rel_path), records)
    return root_info
