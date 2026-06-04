# -*- coding: utf-8 -*-
"""Build a single-file Windows executable with PyInstaller."""

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RES_DIR = ROOT / 'build' / 'exe_resources'
TEMPLATE_INCLUDE = set()  # include all templates
EXE_NAME = 'ContractLedgerTool'


def reset_dir(path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def prepare_resources():
    reset_dir(RES_DIR)
    templates_out = RES_DIR / 'templates'
    uploads_out = RES_DIR / 'uploads'
    static_out = RES_DIR / 'static'
    templates_out.mkdir(parents=True, exist_ok=True)
    uploads_out.mkdir(parents=True, exist_ok=True)

    shutil.copytree(ROOT / 'static', static_out)

    # Copy version.txt for auto-update mechanism
    version_src = ROOT / 'version.txt'
    if version_src.is_file():
        copy_file(version_src, RES_DIR / 'version.txt')

    for html in sorted((ROOT / 'templates').glob('*.html')):
        copy_file(html, templates_out / html.name)

    copied_uploads = set()
    copied_templates = []
    for tpl_path in sorted((ROOT / 'templates').glob('*.contract-template')):
        if TEMPLATE_INCLUDE and tpl_path.name not in TEMPLATE_INCLUDE:
            continue
        with tpl_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        copy_file(tpl_path, templates_out / tpl_path.name)
        copied_templates.append(tpl_path.name)
        source_docx = data.get('source_docx')
        if source_docx:
            src = ROOT / 'uploads' / source_docx
            if not src.exists():
                raise FileNotFoundError(f'Missing source docx: {src}')
            copy_file(src, uploads_out / source_docx)
            copied_uploads.add(source_docx)

    return {
        'templates': copied_templates,
        'uploads': sorted(copied_uploads),
    }


def main():
    manifest = prepare_resources()
    dist_path = ROOT / 'dist' / 'exe'
    work_path = ROOT / 'build' / 'pyinstaller'
    spec_path = ROOT / 'build' / 'pyinstaller_spec'
    dist_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    spec_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--onefile',
        '--console',
        '--name', EXE_NAME,
        '--distpath', str(dist_path),
        '--workpath', str(work_path),
        '--specpath', str(spec_path),
        '--hidden-import', 'pythoncom',
        '--hidden-import', 'pywintypes',
        '--hidden-import', 'win32com',
        '--hidden-import', 'win32com.client',
        '--add-data', f'{RES_DIR / "templates"};templates',
        '--add-data', f'{RES_DIR / "static"};static',
        '--add-data', f'{RES_DIR / "uploads"};uploads',
        str(ROOT / 'app.py'),
    ]
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{EXE_NAME}.exe'
    print(json.dumps({
        'exe': str(exe_path),
        'size_mb': round(exe_path.stat().st_size / 1024 / 1024, 2),
        **manifest,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
