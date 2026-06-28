# -*- coding: utf-8 -*-
"""PyInstaller 打包公共模块 — 统一 hidden-imports、资源准备、目录工具。

build_exe / build_desktop_exe / build_installer 共用此模块，
避免隐藏导入清单三份不一致的问题。
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# ── 统一的 PyInstaller 隐藏导入清单 ──
HIDDEN_IMPORTS = [
    'pythoncom',
    'pywintypes',
    'win32com',
    'win32com.client',
    'jinja2.ext',
    'openpyxl.cell._writer',
    'pdfplumber',
    'pytesseract',
    'pypdfium2',
]

# ── 测试模板，打包时排除 ──
SKIP_TEMPLATE_NAMES = {
    'test.contract-template',
    'Template1_Test.contract-template',
    'Template2_Test.contract-template',
}


def reset_dir(path):
    """清空并重建目录。"""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src, dst):
    """复制单个文件，确保父目录存在。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src, dst):
    """复制目录树，排除 __pycache__。"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))


def collect_contract_templates(templates_dir, uploads_dir):
    """收集合同模板及其引用的 source_docx，返回 (copied_templates, copied_uploads, skipped)。"""
    copied_templates = []
    copied_uploads = set()
    skipped = []

    for ct_path in sorted((ROOT / 'templates').glob('*.contract-template')):
        if ct_path.name in SKIP_TEMPLATE_NAMES:
            skipped.append(f'{ct_path.name} (test)')
            continue

        try:
            with ct_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            skipped.append(f'{ct_path.name} (parse error: {e})')
            continue

        copy_file(ct_path, templates_dir / ct_path.name)
        copied_templates.append(ct_path.name)

        source_docx = data.get('source_docx', '')
        if source_docx:
            src = ROOT / 'uploads' / source_docx
            if src.exists():
                copy_file(src, uploads_dir / source_docx)
                copied_uploads.add(source_docx)
            # source_docx 缺失时模板仍可用（generate_from_scratch 回退）

    return copied_templates, sorted(copied_uploads), skipped


def copy_html_templates(templates_dir):
    """复制所有 HTML 模板（含子目录），返回相对路径列表。"""
    copied = []
    for html in sorted((ROOT / 'templates').rglob('*.html')):
        rel_path = html.relative_to(ROOT / 'templates')
        copy_file(html, templates_dir / rel_path)
        copied.append(str(rel_path))
    return copied


def write_version_file(target_dir, version_str=None):
    """写入 version.txt。"""
    version = version_str or datetime.now().strftime('%Y%m%d.%H%M%S')
    (target_dir / 'version.txt').write_text(version, encoding='utf-8')
    return version


def build_pyinstaller_cmd(entry_script, name, dist_path, work_path, spec_path,
                         res_dir, extra_data=None, icon_path=None):
    """构建 PyInstaller 命令行参数列表。

    extra_data: 额外的 (src, dst_semicolon) 元组列表，用于 --add-data。
    icon_path: 可选的图标文件路径。
    """
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--onefile',
        '--console',
        '--name', name,
        '--distpath', str(dist_path),
        '--workpath', str(work_path),
        '--specpath', str(spec_path),
    ]

    for imp in HIDDEN_IMPORTS:
        cmd.extend(['--hidden-import', imp])

    if icon_path and Path(icon_path).is_file():
        cmd.extend(['--icon', str(icon_path)])

    # 标准 --add-data 项
    add_data_items = [
        (res_dir / 'templates', 'templates'),
        (res_dir / 'static', 'static'),
        (res_dir / 'uploads', 'uploads'),
        (res_dir / 'version.txt', '.'),
    ]

    if extra_data:
        add_data_items.extend(extra_data)

    for src, dst_sep in add_data_items:
        src_path = src if isinstance(src, Path) else Path(src)
        if src_path.exists():
            cmd.extend(['--add-data', f'{src_path};{dst_sep}'])

    cmd.append(str(entry_script))
    return cmd
