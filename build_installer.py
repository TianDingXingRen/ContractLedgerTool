# -*- coding: utf-8 -*-
"""Build the offline installer zip and single-file EXE.

The installer embeds a PyInstaller-built application EXE, so target machines do
not need Python, pip, or internet access.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

from _pyinstaller_common import (
    ROOT, reset_dir, copy_file, copy_tree, build_pyinstaller_cmd,
    prepare_app_resources as _prepare_resources, write_windows_version_info,
)


DIST = ROOT / 'dist'
RELEASE_DIR = DIST / 'release'
ASSETS = ROOT / 'installer_assets'
APP_RES_DIR = ROOT / 'build' / 'offline_app_resources'
APP_DIST_DIR = ROOT / 'build' / 'offline_app_dist'
INSTALLER_STAGE_DIR = ROOT / 'build' / 'offline_installer_package'
SIGN_SCRIPT = ROOT / 'scripts' / 'sign_installer.ps1'
ICON_PATH = ROOT / 'design' / 'icon-options' / 'app-icon.ico'
APP_EXE_NAME = 'ContractLedgerTool'
INSTALLER_EXE_NAME = 'ContractLedgerTool_OfflineInstaller'

LEGACY_DIST_DIR_PATTERNS = (
    'ContractLedgerTool_OfflineInstaller_*',
    'ContractLedgerTool_OnlineInstaller_*',
    'ContractLedgerTool_EXE_*',
    'test_install_*',
)
LEGACY_DIST_DIR_NAMES = {
    'ContractLedgerTool',
    'desktop_exe',
    'exe',
    'installer_exe',
    'offline_app_exe',
}
LEGACY_DIST_FILE_PATTERNS = (
    'ContractLedgerTool_OfflineInstaller_*.zip',
    'ContractLedgerTool_OnlineInstaller_*.zip',
    'ContractLedgerTool_EXE_*.zip',
)
LEGACY_DIST_FILE_NAMES = {
    'ContractLedgerTool_v1.0.zip',
    'ContractTool_Setup.exe',
    'installer.sed',
    'package.zip',
    'setup.bat',
    'stub.bat',
}


def _dist_child(path):
    dist_root = DIST.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(dist_root)
    except ValueError as exc:
        raise RuntimeError(f'Refusing to clean path outside dist: {resolved}') from exc
    return resolved


def _remove_dist_path(path):
    target = _dist_child(path)
    if not target.exists():
        return False
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return True


def clean_legacy_dist_outputs():
    """Keep dist focused on the single publishable offline installer."""
    DIST.mkdir(parents=True, exist_ok=True)
    removed = []
    candidates = []
    for pattern in LEGACY_DIST_DIR_PATTERNS:
        candidates.extend(path for path in DIST.glob(pattern) if path.is_dir())
    candidates.extend(DIST / name for name in LEGACY_DIST_DIR_NAMES)
    for pattern in LEGACY_DIST_FILE_PATTERNS:
        candidates.extend(path for path in DIST.glob(pattern) if path.is_file())
    candidates.extend(DIST / name for name in LEGACY_DIST_FILE_NAMES)

    for path in sorted(set(candidates), key=lambda item: str(item).lower()):
        try:
            if _remove_dist_path(path):
                removed.append(str(path))
        except Exception as exc:
            print(f'SKIP legacy cleanup: {path} ({exc})')
    return removed


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


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().upper()


def prepare_app_resources():
    # Release versions are stable and traceable. Rebuilding changed resources
    # requires an intentional version bump instead of a timestamp-only build ID.
    return _prepare_resources(APP_RES_DIR, write_version=True)


def build_app_exe():
    dist_path = APP_DIST_DIR
    work_path = ROOT / 'build' / 'offline_app_pyinstaller'
    spec_path = ROOT / 'build' / 'offline_app_spec'
    reset_dir(dist_path)
    reset_dir(work_path)
    reset_dir(spec_path)

    extra_data = [
        (ASSETS / 'start.ps1', '.'),
        (ASSETS / 'stop.ps1', '.'),
    ]

    cmd = build_pyinstaller_cmd(
        ROOT / 'app.py', APP_EXE_NAME, dist_path, work_path, spec_path,
        APP_RES_DIR, extra_data=extra_data, icon_path=ICON_PATH,
    )
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
        except Exception as input_exc:
            print(f'无法等待退出确认：{input_exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
''',
        encoding='utf-8',
    )


def build_installer_exe(stage):
    bootstrap = ROOT / 'build' / 'offline_installer_bootstrap.py'
    write_bootstrap(bootstrap)

    dist_path = RELEASE_DIR
    work_path = ROOT / 'build' / 'installer_pyinstaller'
    spec_path = ROOT / 'build' / 'installer_spec'
    reset_dir(dist_path)
    reset_dir(work_path)
    reset_dir(spec_path)

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
    ]

    if ICON_PATH.is_file():
        cmd.extend(['--icon', str(ICON_PATH)])

    version_info = write_windows_version_info(spec_path, INSTALLER_EXE_NAME)
    cmd.extend(['--version-file', str(version_info)])

    cmd.extend([
        '--add-data', f'{stage};installer_package',
        str(bootstrap),
    ])
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{INSTALLER_EXE_NAME}.exe'
    sign_file(exe_path)
    return exe_path


def main():
    if os.environ.get('REQUIRE_CODE_SIGNING') == '1' and not should_sign():
        raise RuntimeError(
            '正式发布要求代码签名，请配置 CODESIGN_PFX 或 '
            'CODESIGN_CERT_THUMBPRINT'
        )
    removed = clean_legacy_dist_outputs()
    stage = INSTALLER_STAGE_DIR

    app_manifest = prepare_app_resources()
    app_exe = build_app_exe()

    reset_dir(stage)
    copy_tree(ASSETS, stage)
    copy_file(app_exe, stage / f'{APP_EXE_NAME}.exe')
    copy_file(ROOT / 'setup_autostart.ps1', stage / 'setup_autostart.ps1')
    copy_file(ROOT / 'setup_autostart_remove.ps1', stage / 'setup_autostart_remove.ps1')
    copy_file(ROOT / 'version.txt', stage / 'version.txt')
    normalize_powershell_encoding(stage)

    exe_path = build_installer_exe(stage)

    manifest = {
        'mode': 'offline',
        'exe': str(exe_path),
        'release_dir': str(RELEASE_DIR),
        'stage': str(stage),
        'app_exe': str(app_exe),
        'exe_size_mb': round(exe_path.stat().st_size / 1024 / 1024, 2),
        'app_exe_size_mb': round(app_exe.stat().st_size / 1024 / 1024, 2),
        'exe_sha256': file_sha256(exe_path),
        'app_exe_sha256': file_sha256(app_exe),
        'code_signing_requested': should_sign(),
        'legacy_dist_removed': len(removed),
        **app_manifest,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
