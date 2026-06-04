# -*- coding: utf-8 -*-
"""构建双击即用的独立 EXE 安装包，直接输出到桌面。

PyInstaller --onefile 打包：包含 Python + 全部依赖 + 模板 + 静态资源。
缺失 source_docx 的模板自动跳过，测试模板自动排除。
双击 EXE 自动启动服务并打开浏览器。
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DESKTOP = Path(os.environ['USERPROFILE']) / 'Desktop'
RES_DIR = ROOT / 'build' / 'desktop_exe_resources'
EXE_NAME = 'ContractLedgerTool'
OUTPUT_DIR = ROOT / 'dist' / 'desktop_exe'

SKIP_TEMPLATE_NAMES = {
    'test.contract-template',
    'Template1_Test.contract-template',
    'Template2_Test.contract-template',
}


def reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path):
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
    print('  static/')

    for html in sorted((ROOT / 'templates').glob('*.html')):
        copy_file(html, templates_out / html.name)
    print(f'  templates/ ({len(list((ROOT / "templates").glob("*.html")))} html)')

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

        source_docx = data.get('source_docx', '')
        if source_docx:
            src = ROOT / 'uploads' / source_docx
            if src.exists():
                copy_file(ct_path, templates_out / ct_path.name)
                copy_file(src, uploads_out / source_docx)
                copied_templates.append(ct_path.name)
                copied_uploads.add(source_docx)
            else:
                # source_docx 缺失但模板仍可用（generate_from_scratch 回退）
                copy_file(ct_path, templates_out / ct_path.name)
                copied_templates.append(ct_path.name)
                print(f'  [warn] {ct_path.name}: source_docx not found, using generate_from_scratch')
        else:
            copy_file(ct_path, templates_out / ct_path.name)
            copied_templates.append(ct_path.name)

    print(f'  templates/ ({len(copied_templates)} contract-templates, {len(copied_uploads)} source docx)')
    for s in skipped:
        print(f'  [skip] {s}')

    version_stamp = datetime.now().strftime('%Y%m%d.%H%M%S')
    (RES_DIR / 'version.txt').write_text(version_stamp, encoding='utf-8')

    return {
        'version': version_stamp,
        'templates': copied_templates,
        'uploads': sorted(copied_uploads),
        'skipped': skipped,
    }


def build_exe():
    dist_path = OUTPUT_DIR
    work_path = ROOT / 'build' / 'pyinstaller_desktop'
    spec_path = ROOT / 'build' / 'pyinstaller_desktop_spec'

    reset_dir(dist_path)
    reset_dir(work_path)
    reset_dir(spec_path)

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
        '--hidden-import', 'jinja2.ext',
        '--hidden-import', 'openpyxl.cell._writer',
        '--add-data', f'{RES_DIR / "templates"};templates',
        '--add-data', f'{RES_DIR / "static"};static',
        '--add-data', f'{RES_DIR / "uploads"};uploads',
        '--add-data', f'{RES_DIR / "version.txt"};.',
        str(ROOT / 'app.py'),
    ]
    print('\n[build] PyInstaller --onefile ...')
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{EXE_NAME}.exe'
    if not exe_path.is_file():
        raise FileNotFoundError(f'EXE not generated at {exe_path}')
    return exe_path


def copy_to_desktop(exe_path: Path, version: str):
    dest_name = f'ContractLedgerTool_v{version[:8]}.exe'
    dest_path = DESKTOP / dest_name
    shutil.copy2(exe_path, dest_path)
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    return dest_path, size_mb


def main():
    print('=' * 55)
    print('  Contract Ledger Tool - Desktop EXE Builder')
    print('=' * 55)
    print()

    print('[1/3] Preparing resources ...')
    manifest = prepare_resources()

    print(f'\n[2/3] Building with PyInstaller ...')
    exe_path = build_exe()
    exe_size = round(exe_path.stat().st_size / (1024 * 1024), 2)
    print(f'  -> {exe_path} ({exe_size} MB)')

    print(f'\n[3/3] Copying to Desktop ...')
    dest_path, dest_size = copy_to_desktop(exe_path, manifest['version'])

    shutil.rmtree(RES_DIR, ignore_errors=True)

    print(f'\n{"=" * 55}')
    print(f'  Done!  EXE on Desktop:')
    print(f'  {dest_path}')
    print(f'  Size: {dest_size:.1f} MB')
    print(f'')
    print(f'  Usage:')
    print(f'  1. Double-click {dest_path.name}')
    print(f'  2. Server starts, browser opens http://127.0.0.1:5000/')
    print(f'  3. Close console window to stop')
    print(f'{"=" * 55}')
    print(f'\n  Included: {len(manifest["templates"])} templates, {len(manifest["uploads"])} source docs')
    if manifest['skipped']:
        print(f'  Skipped: {len(manifest["skipped"])} files')


if __name__ == '__main__':
    main()
