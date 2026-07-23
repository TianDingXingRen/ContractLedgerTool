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
        windowed=True,
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

import ctypes
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_ICONERROR = 0x00000010


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


def _message_box(message: str, *, error: bool = False) -> None:
    flags = MB_OK | (MB_ICONERROR if error else MB_ICONINFORMATION)
    ctypes.windll.user32.MessageBoxW(None, message, '合同管理工具安装程序', flags)


def _argument_value(name: str, default: str) -> str:
    target = name.casefold()
    arguments = sys.argv[1:]
    for index, value in enumerate(arguments[:-1]):
        if value.casefold() == target:
            return arguments[index + 1]
    return default


def _default_install_dir() -> str:
    local_app_data = os.environ.get('LOCALAPPDATA')
    if not local_app_data:
        local_app_data = str(Path.home() / 'AppData' / 'Local')
    return str(Path(local_app_data) / 'Programs' / 'ContractLedgerTool')


def _desktop_dir() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(
        None, 0x0010, None, 0, buffer
    )
    if result == 0 and buffer.value:
        return Path(buffer.value).resolve()
    return (Path.home() / 'Desktop').resolve()


def _is_desktop_path(path: str) -> bool:
    candidate = Path(os.path.expandvars(path)).expanduser().resolve()
    desktop = _desktop_dir()
    return candidate == desktop or desktop in candidate.parents


def _choose_install_dir(default: str) -> str | None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title('采购业务平台安装程序')
    root.resizable(False, False)
    root.attributes('-topmost', True)
    selected = {'path': None}
    path_value = tk.StringVar(value=default)

    frame = ttk.Frame(root, padding=(24, 22, 24, 20))
    frame.grid(row=0, column=0, sticky='nsew')
    frame.columnconfigure(0, weight=1)
    ttk.Label(
        frame, text='选择安装位置', font=('Microsoft YaHei UI', 15, 'bold')
    ).grid(row=0, column=0, columnspan=2, sticky='w')
    ttk.Label(
        frame,
        text='程序和业务数据将保存在该专用目录；不能安装到桌面。',
    ).grid(row=1, column=0, columnspan=2, sticky='w', pady=(6, 14))
    path_entry = ttk.Entry(frame, textvariable=path_value, width=68)
    path_entry.grid(row=2, column=0, sticky='ew', padx=(0, 8))

    def browse() -> None:
        initial = Path(os.path.expandvars(path_value.get())).expanduser()
        while not initial.exists() and initial != initial.parent:
            initial = initial.parent
        chosen = filedialog.askdirectory(
            parent=root,
            title='选择采购业务平台的安装位置',
            initialdir=str(initial),
            mustexist=True,
        )
        if chosen:
            candidate = Path(chosen)
            if candidate.name.casefold() != 'contractledgertool':
                candidate /= 'ContractLedgerTool'
            path_value.set(str(candidate))

    ttk.Button(frame, text='浏览…', command=browse).grid(row=2, column=1)
    ttk.Label(
        frame,
        text='建议保留默认路径；桌面只会创建一个快捷方式。',
        foreground='#5f6368',
    ).grid(row=3, column=0, columnspan=2, sticky='w', pady=(8, 20))

    def accept() -> None:
        raw = path_value.get().strip()
        if not raw:
            messagebox.showerror('安装路径无效', '安装路径不能为空。', parent=root)
            return
        try:
            resolved = str(Path(os.path.expandvars(raw)).expanduser().resolve())
        except OSError as exc:
            messagebox.showerror('安装路径无效', str(exc), parent=root)
            return
        if _is_desktop_path(resolved):
            messagebox.showerror(
                '不能安装到桌面',
                '请选择“本地应用数据”、D 盘应用目录或其他专用文件夹。',
                parent=root,
            )
            return
        selected['path'] = resolved
        root.destroy()

    def cancel() -> None:
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=2, sticky='e')
    ttk.Button(buttons, text='取消', command=cancel).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text='安装', command=accept).grid(row=0, column=1)
    root.protocol('WM_DELETE_WINDOW', cancel)
    root.update_idletasks()
    width, height = root.winfo_reqwidth(), root.winfo_reqheight()
    left = max(0, (root.winfo_screenwidth() - width) // 2)
    top = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f'{width}x{height}+{left}+{top}')
    path_entry.focus_set()
    root.after(300, lambda: root.attributes('-topmost', False))
    root.mainloop()
    return selected['path']


def _installed_url(output: bytes, fallback_port: str) -> str:
    match = re.search(rb'Local URL:\s*(http://127\.0\.0\.1:\d+/)', output)
    if match:
        return match.group(1).decode('ascii')
    return f'http://127.0.0.1:{fallback_port}/'


def main() -> int:
    log_path = Path(tempfile.gettempdir()) / 'ContractLedgerTool-installer.log'
    try:
        payload = _payload_root()
        script = payload / 'install.ps1'
        arguments = list(sys.argv[1:])
        install_dir = _argument_value('-InstallDir', '')
        if not install_dir:
            install_dir = _choose_install_dir(_default_install_dir())
            if not install_dir:
                _message_box('安装已取消。')
                return 0
            arguments.extend(['-InstallDir', install_dir])
        cmd = [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(script),
            *arguments,
        ]
        completed = subprocess.run(
            cmd,
            cwd=str(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
        log_path.write_bytes(completed.stdout or b'')
        if completed.returncode != 0:
            _message_box(
                f'安装失败。\n\n请将日志提供给技术人员：\n{log_path}',
                error=True,
            )
            return completed.returncode

        port = _argument_value('-Port', '5000')
        url = _installed_url(completed.stdout or b'', port)
        no_start = any(arg.casefold() == '-nostart' for arg in sys.argv[1:])
        no_autostart = any(arg.casefold() == '-noautostart' for arg in sys.argv[1:])
        lines = ['安装完成。', '', f'安装位置：{install_dir}']
        if not no_start:
            lines.extend(['后台服务已静默启动。', '', f'浏览器访问：{url}'])
        if not no_autostart:
            lines.extend(['', '登录 Windows 后，服务会自动在后台启动。'])
        _message_box('\n'.join(lines))
        return 0
    except Exception as exc:
        try:
            log_path.write_text(f'安装器启动失败：{exc}', encoding='utf-8')
        except OSError:
            pass
        _message_box(f'安装器启动失败：{exc}\n\n日志：{log_path}', error=True)
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
        '--windowed',
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
