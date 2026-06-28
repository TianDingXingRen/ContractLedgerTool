"""Security utilities: CSRF, path traversal prevention, input validation."""

from __future__ import annotations

import os
import hmac as _hmac
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
