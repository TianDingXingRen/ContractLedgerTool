"""Project file paths and immutable upload storage."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent / 'output' / 'procurement'

FOLDER_NAMES = {
    'inquiry': '02_询价函',
    'quote_template': '03_报价模板',
    'supplier_quote': '04_供应商报价',
    'supplier_quote_pdf': '04_供应商报价',
    'comparison': '05_横向比价',
    'clarification': '06_澄清文件',
    'negotiation_plan': '07_谈判预案',
    'negotiation': '08_谈判纪要',
    'award': '09_成交建议',
    'contract': '10_合同资料',
    'archive': '11_归档包',
}


def configure_base_dir(path):
    global BASE_DIR
    BASE_DIR = Path(path).resolve()
    BASE_DIR.mkdir(parents=True, exist_ok=True)


def _safe_part(value, fallback='item'):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', str(value or '')).strip(' ._')
    return (text or fallback)[:80]


def project_root(project):
    folder = f"{_safe_part(project['project_no'], 'project')}_{_safe_part(project['project_name'], '采购项目')}"
    root = (BASE_DIR / folder).resolve()
    if BASE_DIR not in root.parents:
        raise ValueError('采购项目目录无效')
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_project_folders(project):
    root = project_root(project)
    for name in FOLDER_NAMES.values():
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def target_path(project, file_type, original_name, unique=True):
    root = ensure_project_folders(project)
    folder = root / FOLDER_NAMES.get(file_type, _safe_part(file_type, '其他文件'))
    raw_suffix = Path(os.path.basename(str(original_name or 'file'))).suffix.lower()
    if raw_suffix == '.xlsx':
        suffix = '.xlsx'
    elif raw_suffix == '.docx':
        suffix = '.docx'
    elif raw_suffix == '.pdf':
        suffix = '.pdf'
    elif raw_suffix == '.zip':
        suffix = '.zip'
    elif raw_suffix == '.csv':
        suffix = '.csv'
    else:
        suffix = ''
    token = uuid.uuid4().hex if unique else 'artifact'
    path = (folder / f'{token}{suffix}').resolve()
    if root not in path.parents:
        raise ValueError('目标文件路径无效')
    return path


def relative_path(path):
    resolved = Path(path).resolve()
    if BASE_DIR not in resolved.parents:
        raise ValueError('文件不在采购运行目录内')
    return resolved.relative_to(BASE_DIR).as_posix()


def absolute_path(relative):
    path = (BASE_DIR / str(relative or '')).resolve()
    if BASE_DIR not in path.parents:
        raise ValueError('项目文件路径无效')
    return path


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_upload(project, file_type, file_storage):
    path = target_path(project, file_type, file_storage.filename or 'upload.xlsx')
    file_storage.save(path)
    return {
        'absolute_path': str(path),
        'relative_path': relative_path(path),
        'original_name': os.path.basename(file_storage.filename or path.name),
        'sha256': sha256_file(path),
        'size_bytes': path.stat().st_size,
    }


def save_generated(
    project,
    file_type,
    original_name,
    writer,
    *,
    record_type=None,
):
    """Atomically write and register a generated project artifact."""
    import procurement_store

    path = target_path(project, file_type, original_name)
    stage = path.with_name(
        f'.{path.stem}.{uuid.uuid4().hex}.stage{path.suffix}'
    )
    finalized = False
    try:
        writer(stage)
        if not stage.is_file() or stage.stat().st_size <= 0:
            raise ValueError('生成的项目文件为空')
        os.replace(stage, path)
        finalized = True
        procurement_store.register_project_file(
            project['id'],
            record_type or file_type,
            relative_path(path),
            original_name,
            sha256_file(path),
            path.stat().st_size,
        )
        return path
    except Exception:
        try:
            stage.unlink(missing_ok=True)
        except OSError:
            logging.getLogger('contract_tool').warning(
                'Failed to remove generated project staging file',
                exc_info=True,
            )
        if finalized:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger('contract_tool').error(
                    'Failed to remove unregistered generated project file',
                    exc_info=True,
                )
        raise
