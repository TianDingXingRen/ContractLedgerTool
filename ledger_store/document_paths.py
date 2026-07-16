"""Portable storage rules for generated contract document paths."""

from __future__ import annotations

import os

from utils.security import path_within


LEGACY_OUTPUT_MARKER = '/output/'


def runtime_base_dir(data_dir, db_path):
    """Find the runtime root associated with the active ledger database."""
    try:
        from runtime.app_state import app_state

        if app_state.is_configured() and path_within(app_state.base_dir, db_path):
            return app_state.base_dir
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(data_dir))


def to_portable(path, base_dir):
    """Store runtime-owned documents relative to the runtime root."""
    raw = str(path or '').strip()
    if not raw:
        return ''
    if not os.path.isabs(raw):
        return raw.replace('\\', '/')
    if path_within(base_dir, raw):
        return os.path.relpath(os.path.abspath(raw), base_dir).replace(os.sep, '/')
    return raw


def resolve(path, base_dir):
    """Resolve a portable path and rebase missing legacy output paths."""
    raw = str(path or '').strip()
    if not raw:
        return ''
    if os.path.isabs(raw) and os.path.exists(raw):
        return os.path.abspath(raw)

    relative = raw.replace('\\', '/')
    if os.path.isabs(raw):
        normalized = '/' + relative.lstrip('/')
        index = normalized.lower().rfind(LEGACY_OUTPUT_MARKER)
        if index < 0:
            return os.path.abspath(raw)
        relative = normalized[index + 1:]

    candidate = os.path.abspath(os.path.join(base_dir, relative.replace('/', os.sep)))
    if path_within(base_dir, candidate):
        return candidate
    return os.path.abspath(raw)


def normalize_contract_paths(conn, base_dir):
    """Rewrite runtime-owned absolute document paths to their portable form."""
    rows = conn.execute(
        "SELECT id, docx_path FROM contracts WHERE docx_path IS NOT NULL AND docx_path != ''"
    ).fetchall()
    updated = 0
    for row in rows:
        stored = to_portable(row['docx_path'], base_dir)
        if stored != row['docx_path']:
            conn.execute(
                'UPDATE contracts SET docx_path = ? WHERE id = ?',
                (stored, row['id']),
            )
            updated += 1
    return updated
