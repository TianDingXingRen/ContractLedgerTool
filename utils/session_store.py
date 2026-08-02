"""Filesystem-backed editor session persistence."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from runtime.paths import RuntimePaths
from utils.security import safe_join_file


def save_session_data(
    sid: str,
    data: dict[str, Any],
    paths: RuntimePaths,
) -> None:
    """Atomically persist one session below ``paths.sessions_dir``."""
    path = safe_join_file(
        str(paths.sessions_dir),
        f'{sid}.json',
        allowed_ext={'.json'},
    )
    tmp = path + f'.tmp-{uuid.uuid4().hex}'
    try:
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            logging.getLogger('contract_tool').debug(
                '会话暂存文件已不存在: %s',
                tmp,
            )


def load_session_data(
    sid: str,
    paths: RuntimePaths,
) -> dict[str, Any]:
    """Load one session from ``paths.sessions_dir``."""
    path = safe_join_file(
        str(paths.sessions_dir),
        f'{sid}.json',
        allowed_ext={'.json'},
    )
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)
