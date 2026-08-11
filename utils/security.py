"""Security utilities: CSRF, path traversal prevention, input validation."""

from __future__ import annotations

import os
import hmac as _hmac
import zipfile
from pathlib import PurePosixPath
from typing import Optional


# ── Input limits ──
MAX_TEMPLATE_FIELDS: int = 200
MAX_TABLE_COLUMNS: int = 50
MAX_TABLE_ROWS: int = 500
MAX_BATCH_CONTRACTS: int = 100
MAX_PLAN_ROWS: int = 300
MAX_TEXT_VALUE_LENGTH: int = 10000
MAX_COUNTERPARTY_LENGTH: int = 120
MAX_PROJECT_NAME_LENGTH: int = 120
MAX_SUBSYSTEM_NAME_LENGTH: int = 120
MAX_OFFICE_ARCHIVE_MEMBERS: int = 2000
MAX_OFFICE_ARCHIVE_UNCOMPRESSED: int = 100 * 1024 * 1024
MAX_OFFICE_ARCHIVE_MEMBER_SIZE: int = 50 * 1024 * 1024
MAX_OFFICE_COMPRESSION_RATIO: int = 200


def hmac_compare(left: str, right: str) -> bool:
    """Constant-time string comparison."""
    try:
        return _hmac.compare_digest(str(left), str(right))
    except Exception:
        return False


def path_within(root: str, path: str) -> bool:
    """Check that path is within root directory (traversal guard)."""
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    try:
        return os.path.commonpath([root_abs, path_abs]) == root_abs
    except ValueError:
        return False


def safe_join_file(root: str, filename: str, allowed_ext: Optional[set[str]] = None) -> str:
    """Join and validate a filename within root. Raises ValueError on invalid input."""
    name = str(filename or '')
    basename = os.path.basename(name)
    if not basename or basename != name or os.path.isabs(name):
        raise ValueError('文件名无效')
    if allowed_ext and os.path.splitext(basename)[1].lower() not in allowed_ext:
        raise ValueError('文件类型无效')
    path = os.path.abspath(os.path.join(root, basename))
    if not path_within(root, path):
        raise ValueError('文件路径无效')
    return path


def limit_text(value, max_len: int = MAX_TEXT_VALUE_LENGTH) -> str:
    """Truncate text to max_len characters."""
    text = str(value or '')
    return text[:max_len]


def safe_spreadsheet_value(value):
    """Keep untrusted text from becoming an Excel formula."""
    if isinstance(value, str) and value.startswith('='):
        return "'" + value
    return value


def bounded_int(value, default: int = 0, min_value: int = 0,
                max_value: int = 100000, label: str = '数值') -> int:
    """Parse and validate an integer within bounds."""
    text = str(value or '').strip()
    if text == '':
        return default
    try:
        parsed = int(text)
    except ValueError:
        raise ValueError(f'{label}必须是整数')
    if parsed < min_value or parsed > max_value:
        raise ValueError(f'{label}超出允许范围')
    return parsed


def bounded_decimal_places(value) -> int:
    """Parse decimal_places in range 0-6, default 2."""
    return bounded_int(value, default=2, min_value=0, max_value=6, label='小数位')


def validate_office_archive(path: str) -> None:
    """Reject malformed, traversing, or suspiciously compressed DOCX/XLSX files."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_OFFICE_ARCHIVE_MEMBERS:
                raise ValueError('Office 文件包含异常数量的内部文件')
            total_size = 0
            names = set()
            for member in members:
                normalized = str(member.filename or '').replace('\\', '/')
                internal_path = PurePosixPath(normalized)
                if (
                    not normalized
                    or internal_path.is_absolute()
                    or any(part in {'', '.', '..'} for part in internal_path.parts)
                    or ':' in internal_path.parts[0]
                ):
                    raise ValueError('Office 文件包含不安全的内部路径')
                if normalized in names:
                    raise ValueError('Office 文件包含重复的内部路径')
                names.add(normalized)
                if member.flag_bits & 0x1:
                    raise ValueError('Office 文件不能包含加密内容')
                if member.file_size > MAX_OFFICE_ARCHIVE_MEMBER_SIZE:
                    raise ValueError('Office 文件中的单个内容过大')
                total_size += member.file_size
                if total_size > MAX_OFFICE_ARCHIVE_UNCOMPRESSED:
                    raise ValueError('Office 文件解压后内容过大')
                if member.file_size:
                    compressed_size = max(1, member.compress_size)
                    if member.file_size / compressed_size > MAX_OFFICE_COMPRESSION_RATIO:
                        raise ValueError('Office 文件压缩比异常，可能存在压缩包风险')
            if archive.testzip() is not None:
                raise ValueError('Office 文件内容校验失败')
            suffix = os.path.splitext(str(path))[1].lower()
            required = {
                '.docx': {'[Content_Types].xml', 'word/document.xml'},
                '.xlsx': {'[Content_Types].xml', 'xl/workbook.xml'},
            }.get(suffix, {'[Content_Types].xml'})
            if not required.issubset(names):
                raise ValueError('Office 文件缺少必要的内部结构')
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError('Office 文件结构无效') from exc
