# -*- coding: utf-8 -*-
"""构建双击即用的独立 EXE 安装包，直接输出到桌面。

PyInstaller --onefile 打包：包含 Python + 全部依赖 + 模板 + 静态资源。
缺失 source_docx 的模板自动跳过，测试模板自动排除。
双击 EXE 自动启动服务并打开浏览器。
"""

import os
import shutil
import subprocess
from pathlib import Path

from _pyinstaller_common import (
    ROOT, reset_dir, build_pyinstaller_cmd, prepare_app_resources,
)


DESKTOP = Path(os.environ['USERPROFILE']) / 'Desktop'
RES_DIR = ROOT / 'build' / 'desktop_exe_resources'
EXE_NAME = 'ContractLedgerTool'
OUTPUT_DIR = ROOT / 'dist' / 'desktop_exe'
ICON_PATH = ROOT / 'design' / 'icon-options' / 'app-icon.ico'


def build_exe():
    dist_path = OUTPUT_DIR
    work_path = ROOT / 'build' / 'pyinstaller_desktop'
    spec_path = ROOT / 'build' / 'pyinstaller_desktop_spec'

    reset_dir(dist_path)
    reset_dir(work_path)
    reset_dir(spec_path)

    cmd = build_pyinstaller_cmd(
        ROOT / 'app.py', EXE_NAME, dist_path, work_path, spec_path, RES_DIR,
        icon_path=ICON_PATH,
    )
    print('\n[build] PyInstaller --onefile ...')
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{EXE_NAME}.exe'
    if not exe_path.is_file():
        raise FileNotFoundError(f'EXE not generated at {exe_path}')
    return exe_path


def copy_to_desktop(exe_path, version):
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
    manifest = prepare_app_resources(RES_DIR)
    print(f'  templates/ ({len(manifest["html_templates"])} html)')
    print(f'  templates/ ({len(manifest["templates"])} contract-templates, {len(manifest["uploads"])} source docx)')
    for s in manifest['skipped']:
        print(f'  [skip] {s}')

    print('\n[2/3] Building with PyInstaller ...')
    exe_path = build_exe()
    exe_size = round(exe_path.stat().st_size / (1024 * 1024), 2)
    print(f'  -> {exe_path} ({exe_size} MB)')

    print('\n[3/3] Copying to Desktop ...')
    dest_path, dest_size = copy_to_desktop(exe_path, manifest['version'])

    shutil.rmtree(RES_DIR, ignore_errors=True)

    print(f'\n{"=" * 55}')
    print('  Done!  EXE on Desktop:')
    print(f'  {dest_path}')
    print(f'  Size: {dest_size:.1f} MB')
    print()
    print('  Usage:')
    print(f'  1. Double-click {dest_path.name}')
    print('  2. Server starts, browser opens http://127.0.0.1:5000/')
    print('  3. Close console window to stop')
    print(f'{"=" * 55}')
    print(f'\n  Included: {len(manifest["templates"])} templates, {len(manifest["uploads"])} source docs')
    if manifest['skipped']:
        print(f'  Skipped: {len(manifest["skipped"])} files')


if __name__ == '__main__':
    main()
