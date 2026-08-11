"""Safe archive and SQLite primitives for handover packages."""

from __future__ import annotations

import os
import sqlite3
from pathlib import PurePosixPath

from utils.field_utils import safe_filename_part
from utils.file_digest import sha256_file as _sha256_file, sha256_stream
from utils.logger import get_logger


MAX_FULL_PACKAGE_MEMBERS = 20_000
MAX_FULL_PACKAGE_UNCOMPRESSED = 5 * 1024 * 1024 * 1024
MAX_FULL_PACKAGE_MEMBER_SIZE = 1024 * 1024 * 1024
MAX_FULL_PACKAGE_COMPRESSION_RATIO = 300
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


def read_optional_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as stream:
            return stream.read().strip()
    except OSError:
        return ''


def remove_file_if_exists(directory, filename):
    path = os.path.join(os.path.abspath(directory), os.path.basename(filename))
    try:
        os.remove(path)
    except FileNotFoundError:
        get_logger().debug('Temporary handover file already absent')

def safe_label(value, default='handover'):
    label = safe_filename_part(str(value or '').strip(), default)[:36]
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


def validate_package_archive(zf):
    """Enforce size, path, encryption and compression limits for a package."""
    archive_infos = zf.infolist()
    if not archive_infos or len(archive_infos) > MAX_FULL_PACKAGE_MEMBERS:
        raise ValueError('完整数据包包含异常数量的文件')
    infos = {}
    total_uncompressed = 0
    for info in archive_infos:
        normalized = normalize_archive_name(info.filename)
        if normalized in infos:
            raise ValueError('完整数据包包含重复文件路径')
        if info.flag_bits & 0x1:
            raise ValueError('完整数据包不能包含加密 ZIP 成员')
        if info.file_size > MAX_FULL_PACKAGE_MEMBER_SIZE:
            raise ValueError('完整数据包中的单个文件过大')
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_FULL_PACKAGE_UNCOMPRESSED:
            raise ValueError('完整数据包解压后内容过大')
        ratio = info.file_size / max(1, info.compress_size)
        if ratio > MAX_FULL_PACKAGE_COMPRESSION_RATIO:
            raise ValueError('完整数据包压缩比异常，可能存在压缩包风险')
        infos[normalized] = info
    return archive_infos, infos


def sha256_file(path):
    return _sha256_file(path)


def sha256_zip_member(zf, name):
    with zf.open(name) as stream:
        return sha256_stream(stream)


def copy_database(db_path, target_path):
    if not os.path.isfile(db_path):
        raise FileNotFoundError('数据库文件不存在')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    source = sqlite3.connect(db_path)
    try:
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


def validate_application_database(
    path,
    *,
    max_ledger_version,
    max_procurement_version,
):
    """Validate that a SQLite file is a compatible application database."""
    validate_sqlite_file(path)
    required_tables = {
        'contracts',
        'payment_plans',
        'schema_version',
        'procurement_projects',
        'procurement_schema_version',
    }
    connection = None
    try:
        connection = sqlite3.connect(path)
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        tables = {str(row[0]) for row in table_rows}
        missing = sorted(required_tables - tables)
        if missing:
            raise ValueError(
                f'备份数据库缺少应用表: {", ".join(missing)}'
            )

        ledger_row = connection.execute(
            'SELECT MAX(version) FROM schema_version'
        ).fetchone()
        procurement_row = connection.execute(
            'SELECT MAX(version) FROM procurement_schema_version'
        ).fetchone()
        ledger_version = int(ledger_row[0] or 0) if ledger_row else 0
        procurement_version = (
            int(procurement_row[0] or 0) if procurement_row else 0
        )
        if ledger_version < 1 or procurement_version < 1:
            raise ValueError('备份数据库缺少有效的架构版本记录')
        if ledger_version > int(max_ledger_version):
            raise ValueError(
                f'备份数据库版本过新: {ledger_version} > {max_ledger_version}'
            )
        if procurement_version > int(max_procurement_version):
            raise ValueError(
                '备份采购数据库版本过新: '
                f'{procurement_version} > {max_procurement_version}'
            )
        return {
            'ledger_schema_version': ledger_version,
            'procurement_schema_version': procurement_version,
        }
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'无法验证备份数据库架构: {exc}') from exc
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
