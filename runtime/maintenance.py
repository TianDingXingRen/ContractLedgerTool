"""Runtime maintenance tasks for cleanup and packaged asset seeding."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time

import ledger_store
import template_def
from utils.logger import get_logger


def cleanup_old_files(paths, config, max_age_days=None):
    """Remove expired upload/output/session files for the active runtime."""
    now = time.time()
    file_max_age_days = (
        max_age_days if max_age_days is not None else config.OUTPUT_CLEANUP_DAYS
    )
    cutoff = now - file_max_age_days * 86400

    preserved = set()
    try:
        for path in ledger_store.get_all_docx_paths():
            if path:
                preserved.add(os.path.normpath(os.path.abspath(path)))
    except (OSError, sqlite3.Error, ValueError) as e:
        get_logger().error('无法读取合同台账，跳过文件清理以避免数据丢失：%s', e)
        return

    uploads_safe_to_clean = True
    try:
        for tpl_info in template_def.list_templates():
            tpl_path = tpl_info.get('path', '')
            if not tpl_path or not os.path.isfile(tpl_path):
                continue
            try:
                tpl = template_def.TemplateDef.load(tpl_path)
                source_docx = tpl.data.get('source_docx', '')
                if source_docx:
                    src_path = paths.uploads_dir / source_docx
                    if src_path.is_file():
                        preserved.add(os.path.normpath(os.path.abspath(src_path)))
            except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
                uploads_safe_to_clean = False
                get_logger().warning('模板 %s 加载失败，upload 保护可能不完整', tpl_path, exc_info=True)
    except (OSError, ValueError, json.JSONDecodeError, TypeError, AttributeError) as e:
        uploads_safe_to_clean = False
        get_logger().warning('读取模板列表失败，upload 保护可能不完整：%s', e)

    for folder, label in (
        (paths.uploads_dir, 'uploads'),
        (paths.output_dir, 'output'),
    ):
        if label == 'uploads' and not uploads_safe_to_clean:
            get_logger().warning('存在无法读取的模板，跳过 upload 清理以避免误删源文件')
            continue
        try:
            for item in folder.iterdir():
                if not item.is_file():
                    continue
                if os.path.normpath(os.path.abspath(item)) in preserved:
                    continue
                if item.stat().st_mtime < cutoff:
                    item.unlink()
                    get_logger().info('Cleaned old %s file: %s', label, item.name)
        except Exception as e:
            get_logger().warning('清理 %s 目录时出错：%s', label, e)

    session_cutoff = now - config.SESSION_TTL_HOURS * 3600
    try:
        for item in paths.sessions_dir.iterdir():
            if not item.is_file() or item.suffix != '.json':
                continue
            if item.stat().st_mtime < session_cutoff:
                item.unlink()
                get_logger().info('Cleaned old session file: %s', item.name)
    except Exception as e:
        get_logger().warning('清理 sessions 目录时出错：%s', e)


def seed_packaged_assets(paths):
    """Copy bundled templates, uploads, and launcher scripts to writable paths."""
    if paths.resource_dir == paths.base_dir:
        return

    version_file = paths.resource_dir / 'version.txt'
    current_version = version_file.read_text(encoding='utf-8').strip() if version_file.is_file() else ''

    installed_version_file = paths.base_dir / '.installed_version'
    installed_version = (
        installed_version_file.read_text(encoding='utf-8').strip()
        if installed_version_file.is_file()
        else ''
    )

    if current_version and current_version == installed_version:
        return

    resource_templates = paths.resource_dir / 'templates'
    if resource_templates.is_dir():
        paths.templates_dir.mkdir(parents=True, exist_ok=True)
        for src in resource_templates.iterdir():
            if not src.is_file() or src.suffix != '.contract-template':
                continue
            dst = paths.templates_dir / src.name
            if src.resolve() == dst.resolve():
                continue
            # Runtime templates become user-owned after the first seed.
            if not dst.exists():
                shutil.copy2(src, dst)

    resource_uploads = paths.resource_dir / 'uploads'
    if resource_uploads.is_dir():
        paths.uploads_dir.mkdir(parents=True, exist_ok=True)
        for src in resource_uploads.iterdir():
            if not src.is_file():
                continue
            dst = paths.uploads_dir / src.name
            if src.resolve() == dst.resolve():
                continue
            # Source documents may have been replaced or edited by the user.
            if not dst.exists():
                shutil.copy2(src, dst)

    _seed_launcher_script(paths.resource_dir, paths.base_dir, 'start.ps1')
    _seed_launcher_script(paths.resource_dir, paths.base_dir, 'stop.ps1')

    if current_version:
        installed_version_file.write_text(current_version, encoding='utf-8')


def _seed_launcher_script(resource_dir, target_dir, filename):
    """Copy a single launcher script from resource dir to target dir."""
    candidates = [
        resource_dir / 'installer_assets' / filename,
        resource_dir / filename,
    ]
    dst = target_dir / filename
    if dst.exists():
        return
    for src in candidates:
        if src.is_file():
            shutil.copy2(src, dst)
            try:
                os.chmod(dst, 0o444)
            except OSError:
                pass
            return
