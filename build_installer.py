# -*- coding: utf-8 -*-
"""Build the offline installer zip and single-file EXE.

The installer embeds a PyInstaller-built application EXE, so target machines do
not need Python, pip, or internet access.
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
ASSETS = ROOT / 'installer_assets'
APP_RES_DIR = ROOT / 'build' / 'offline_app_resources'
SIGN_SCRIPT = ROOT / 'scripts' / 'sign_installer.ps1'
APP_EXE_NAME = 'ContractLedgerTool'
INSTALLER_EXE_NAME = 'ContractLedgerTool_OfflineInstaller'
TEMPLATE_INCLUDE = set()  # include all templates


def reset_dir(path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))


def normalize_powershell_encoding(root):
    """Write staged PowerShell scripts with a BOM for Windows PowerShell 5.1."""
    for path in root.rglob('*.ps1'):
        text = path.read_text(encoding='utf-8-sig')
        path.write_text(text, encoding='utf-8-sig')


def should_sign():
    return bool(os.environ.get('CODESIGN_PFX') or os.environ.get('CODESIGN_CERT_THUMBPRINT'))


def sign_file(path):
    if not should_sign():
        print(f'SKIP signing (no CODESIGN_PFX or CODESIGN_CERT_THUMBPRINT): {path}')
        return
    if not SIGN_SCRIPT.is_file():
        raise FileNotFoundError(f'Signing script not found: {SIGN_SCRIPT}')
    cmd = [
        'powershell',
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        str(SIGN_SCRIPT),
        '-FilePath',
        str(path),
    ]
    if os.environ.get('CODESIGN_NO_TIMESTAMP') == '1':
        cmd.append('-NoTimestamp')
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))


def valid_templates():
    result = []
    for path in sorted((ROOT / 'templates').glob('*.contract-template')):
        if TEMPLATE_INCLUDE and path.name not in TEMPLATE_INCLUDE:
            continue
        try:
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            result.append((path, data))
        except Exception:
            print(f'SKIP invalid template: {path.name}')
    return result


def zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src_dir.rglob('*'):
            if path.is_file():
                zf.write(path, path.relative_to(src_dir))


def prepare_app_resources():
    reset_dir(APP_RES_DIR)
    templates_dir = APP_RES_DIR / 'templates'
    uploads_dir = APP_RES_DIR / 'uploads'
    templates_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    copy_tree(ROOT / 'static', APP_RES_DIR / 'static')

    version_src = ROOT / 'version.txt'
    if version_src.is_file():
        copy_file(version_src, APP_RES_DIR / 'version.txt')
    else:
        (APP_RES_DIR / 'version.txt').write_text(
            datetime.now().strftime('%Y%m%d.%H%M%S'),
            encoding='utf-8',
        )

    for html_template in sorted((ROOT / 'templates').glob('*.html')):
        copy_file(html_template, templates_dir / html_template.name)

    copied_uploads = set()
    copied_templates = []
    for template_path, data in valid_templates():
        copy_file(template_path, templates_dir / template_path.name)
        copied_templates.append(template_path.name)
        src_docx = data.get('source_docx')
        if src_docx and src_docx not in copied_uploads:
            src = ROOT / 'uploads' / src_docx
            if src.exists():
                copy_file(src, uploads_dir / src_docx)
                copied_uploads.add(src_docx)

    return {
        'templates': copied_templates,
        'uploads': sorted(copied_uploads),
    }


def build_app_exe():
    dist_path = DIST / 'offline_app_exe'
    work_path = ROOT / 'build' / 'offline_app_pyinstaller'
    spec_path = ROOT / 'build' / 'offline_app_spec'
    reset_dir(dist_path)
    reset_dir(work_path)
    reset_dir(spec_path)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--onefile',
        '--console',
        '--name', APP_EXE_NAME,
        '--distpath', str(dist_path),
        '--workpath', str(work_path),
        '--specpath', str(spec_path),
        '--hidden-import', 'pythoncom',
        '--hidden-import', 'pywintypes',
        '--hidden-import', 'win32com',
        '--hidden-import', 'win32com.client',
        '--hidden-import', 'jinja2.ext',
        '--hidden-import', 'openpyxl.cell._writer',
        '--add-data', f'{APP_RES_DIR / "templates"};templates',
        '--add-data', f'{APP_RES_DIR / "static"};static',
        '--add-data', f'{APP_RES_DIR / "uploads"};uploads',
        '--add-data', f'{APP_RES_DIR / "version.txt"};.',
        '--add-data', f'{ASSETS / "start.ps1"};.',
        '--add-data', f'{ASSETS / "stop.ps1"};.',
        str(ROOT / 'app.py'),
    ]
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{APP_EXE_NAME}.exe'
    if not exe_path.is_file():
        raise FileNotFoundError(f'Application EXE was not generated: {exe_path}')
    sign_file(exe_path)
    return exe_path


def write_bootstrap(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        r'''# -*- coding: utf-8 -*-
"""PyInstaller bootstrapper for the offline installer payload."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _payload_root() -> Path:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    package = base / 'installer_package'
    candidates = [package]
    if package.exists():
        candidates.extend(p for p in package.iterdir() if p.is_dir())
    candidates.append(base)
    for candidate in candidates:
        if (candidate / 'install.ps1').is_file() and (candidate / 'ContractLedgerTool.exe').is_file():
            return candidate
    raise FileNotFoundError('安装包内容不完整：未找到 install.ps1 或 ContractLedgerTool.exe')


def main() -> int:
    try:
        payload = _payload_root()
        script = payload / 'install.ps1'
        cmd = [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(script),
            *sys.argv[1:],
        ]
        return subprocess.run(cmd, cwd=str(payload)).returncode
    except Exception as exc:
        print(f'安装器启动失败：{exc}')
        try:
            input('按 Enter 退出...')
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
''',
        encoding='utf-8',
    )


def build_installer_exe(stage):
    bootstrap = ROOT / 'build' / 'offline_installer_bootstrap.py'
    write_bootstrap(bootstrap)

    dist_path = DIST / 'installer_exe'
    work_path = ROOT / 'build' / 'installer_pyinstaller'
    spec_path = ROOT / 'build' / 'installer_spec'
    dist_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    spec_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--onefile',
        '--console',
        '--name', INSTALLER_EXE_NAME,
        '--distpath', str(dist_path),
        '--workpath', str(work_path),
        '--specpath', str(spec_path),
        '--add-data', f'{stage};installer_package',
        str(bootstrap),
    ]
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{INSTALLER_EXE_NAME}.exe'
    sign_file(exe_path)
    return exe_path


def main():
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    stage = DIST / f'ContractLedgerTool_OfflineInstaller_{stamp}'
    zip_path = stage.with_suffix('.zip')

    app_manifest = prepare_app_resources()
    app_exe = build_app_exe()

    reset_dir(stage)
    copy_tree(ASSETS, stage)
    copy_file(app_exe, stage / f'{APP_EXE_NAME}.exe')
    copy_file(ROOT / 'setup_autostart.ps1', stage / 'setup_autostart.ps1')
    copy_file(ROOT / 'setup_autostart_remove.ps1', stage / 'setup_autostart_remove.ps1')
    normalize_powershell_encoding(stage)

    zip_dir(stage, zip_path)
    exe_path = build_installer_exe(stage)

    manifest = {
        'mode': 'offline',
        'zip': str(zip_path),
        'exe': str(exe_path),
        'stage': str(stage),
        'app_exe': str(app_exe),
        'size_mb': round(zip_path.stat().st_size / 1024 / 1024, 2),
        'exe_size_mb': round(exe_path.stat().st_size / 1024 / 1024, 2),
        'app_exe_size_mb': round(app_exe.stat().st_size / 1024 / 1024, 2),
        **app_manifest,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
