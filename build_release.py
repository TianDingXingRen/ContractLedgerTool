#!/usr/bin/env python
"""打包发布脚本 v2 — 清理后发布"""

import os, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / 'dist'
PKG = DIST_DIR / 'ContractLedgerTool'
ZIP_NAME = 'ContractLedgerTool_v1.0.zip'

EXCLUDE_DIRS = {
    '__pycache__', '.git', 'build', 'dist', 'logs', 'output',
    'uploads', 'sessions', 'data', 'installer_assets', 'scripts', 'versions',
}

EXCLUDE_FILES = {
    'test.contract-template',  # test artifacts
}

INCLUDE_FILES = [
    'app.py', 'config.py', 'docx_builder.py', 'field_eval.py',
    'payment_extractor.py', 'pdf_exporter.py',
    'template_def.py', 'xlsx_exporter.py',
    'requirements.txt', 'README.md', 'version.txt',
]

INCLUDE_DIRS = ['routes', 'utils', 'templates', 'static', 'ledger_store']

_SRC_FILES = set(INCLUDE_FILES)


def ignore(path_str, names):
    rel = Path(path_str).relative_to(ROOT)
    result = set()
    for name in names:
        if name in EXCLUDE_DIRS:
            result.add(name)
            continue
        if str(rel) == 'templates' and name in EXCLUDE_FILES:
            result.add(name)
    return result


def main():
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True, exist_ok=True)

    for d in ['data', 'logs', 'uploads', 'output', 'sessions']:
        (PKG / d).mkdir(exist_ok=True)

    for f in INCLUDE_FILES:
        src = ROOT / f
        if src.exists():
            shutil.copy2(src, PKG / f)
            print(f'  {f}')

    for d in INCLUDE_DIRS:
        src = ROOT / d
        if src.is_dir():
            dst = PKG / d
            shutil.copytree(src, dst, ignore=ignore)
            print(f'  {d}/')

    bat_path = PKG / 'start.bat'
    bat_path.write_text(
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        'cd /d "%~dp0"\r\n'
        'echo ==============================\r\n'
        'echo    Contract Ledger Tool v1.0\r\n'
        'echo ==============================\r\n'
        'echo.\r\n'
        'echo Starting...\r\n'
        'echo If browser does not open, visit http://127.0.0.1:5000/\r\n'
        'echo.\r\n'
        'python app.py\r\n'
        'pause\r\n',
        encoding='ascii',
    )
    print('  start.bat')

    zip_path = Path(os.environ['USERPROFILE']) / 'Desktop' / ZIP_NAME
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(PKG.rglob('*')):
            if fpath.is_file():
                zf.write(fpath, str(fpath.relative_to(DIST_DIR)))
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'\n  {zip_path}')
    print(f'  {size_mb:.1f} MB  —  {len(zf.namelist())} files')


if __name__ == '__main__':
    main()
