"""Optional Windows EFS protection for local business data at rest."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Iterable


FILE_ATTRIBUTE_ENCRYPTED = 0x00004000
FILE_SUPPORTS_ENCRYPTION = 0x00020000
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
MAX_STATUS_FILES = 5000


class DataProtectionError(RuntimeError):
    pass


class WindowsEfsBackend:
    """Small Win32 adapter kept injectable for deterministic tests."""

    def __init__(self):
        if os.name != 'nt':
            raise DataProtectionError('Windows EFS 仅支持 Windows')
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
        self.kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        self.kernel32.GetFileAttributesW.restype = wintypes.DWORD
        self.kernel32.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        self.kernel32.GetVolumeInformationW.restype = wintypes.BOOL
        self.advapi32.EncryptFileW.argtypes = [wintypes.LPCWSTR]
        self.advapi32.EncryptFileW.restype = wintypes.BOOL
        self.advapi32.DecryptFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        self.advapi32.DecryptFileW.restype = wintypes.BOOL

    @staticmethod
    def _raise_last_error(operation: str, path: Path) -> None:
        error = ctypes.get_last_error()
        raise DataProtectionError(f'{operation}失败：{path}（Windows 错误 {error}）')

    def volume_supports_encryption(self, path: Path) -> bool:
        root = Path(path).resolve().anchor
        if not root:
            return False
        flags = wintypes.DWORD()
        ok = self.kernel32.GetVolumeInformationW(
            root, None, 0, None, None, ctypes.byref(flags), None, 0,
        )
        if not ok:
            self._raise_last_error('读取磁盘能力', Path(root))
        return bool(flags.value & FILE_SUPPORTS_ENCRYPTION)

    def is_encrypted(self, path: Path) -> bool:
        attributes = self.kernel32.GetFileAttributesW(str(path))
        if attributes == INVALID_FILE_ATTRIBUTES:
            self._raise_last_error('读取加密属性', path)
        return bool(attributes & FILE_ATTRIBUTE_ENCRYPTED)

    def encrypt(self, path: Path) -> None:
        if not self.advapi32.EncryptFileW(str(path)):
            self._raise_last_error('EFS 加密', path)

    def decrypt(self, path: Path) -> None:
        if not self.advapi32.DecryptFileW(str(path), 0):
            self._raise_last_error('EFS 回滚解密', path)


def _backend():
    return WindowsEfsBackend()


def _protected_roots(runtime_paths) -> list[Path]:
    return [
        Path(runtime_paths.data_dir),
        Path(runtime_paths.templates_dir),
        Path(runtime_paths.uploads_dir),
        Path(runtime_paths.output_dir),
        Path(runtime_paths.sessions_dir),
    ]


def _sensitive_files(runtime_paths) -> list[Path]:
    return [
        Path(runtime_paths.config_file),
        Path(runtime_paths.base_dir) / '.secret_key',
    ]


def _walk_existing(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield existing children without following links outside protected roots."""
    for root in roots:
        if not root.exists() or root.is_symlink():
            continue
        yield root
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name for name in directories
                if not (current_path / name).is_symlink()
            ]
            for name in directories:
                yield current_path / name
            for name in files:
                path = current_path / name
                if not path.is_symlink():
                    yield path


def data_protection_status(runtime_paths, *, backend=None) -> dict:
    warning = (
        'EFS 文件与当前 Windows 用户证书绑定；重装系统或丢失私钥可能导致无法恢复。'
        '启用后请立即导出并妥善保管 EFS 证书和私钥。'
    )
    if os.name != 'nt' and backend is None:
        return {
            'supported': False,
            'enabled': False,
            'partial': False,
            'encrypted_files': 0,
            'unencrypted_files': 0,
            'scan_truncated': False,
            'description': '当前系统不支持 Windows EFS',
            'warning': warning,
        }
    backend = backend or _backend()
    try:
        supported = backend.volume_supports_encryption(Path(runtime_paths.base_dir))
    except DataProtectionError as exc:
        return {
            'supported': False,
            'enabled': False,
            'partial': False,
            'encrypted_files': 0,
            'unencrypted_files': 0,
            'scan_truncated': False,
            'description': str(exc),
            'warning': warning,
        }
    if not supported:
        return {
            'supported': False,
            'enabled': False,
            'partial': False,
            'encrypted_files': 0,
            'unencrypted_files': 0,
            'scan_truncated': False,
            'description': '当前磁盘文件系统不支持 EFS（通常需要 NTFS）',
            'warning': warning,
        }

    encrypted = unencrypted = 0
    truncated = False
    candidates = list(_walk_existing(_protected_roots(runtime_paths)))
    candidates.extend(path for path in _sensitive_files(runtime_paths) if path.is_file())
    for index, path in enumerate(candidates):
        if index >= MAX_STATUS_FILES:
            truncated = True
            break
        try:
            if backend.is_encrypted(path):
                encrypted += 1
            else:
                unencrypted += 1
        except DataProtectionError:
            unencrypted += 1
    partial = encrypted > 0 and unencrypted > 0
    enabled = encrypted > 0 and unencrypted == 0 and not truncated
    if enabled:
        description = f'业务数据已启用 EFS（已检查 {encrypted} 个文件/目录）'
    elif partial:
        description = f'EFS 仅部分生效：{encrypted} 个已加密，{unencrypted} 个未加密'
    else:
        description = '业务数据尚未启用 EFS'
    if truncated:
        description += f'；状态扫描超过 {MAX_STATUS_FILES} 项，结果不完整'
    return {
        'supported': True,
        'enabled': enabled,
        'partial': partial,
        'encrypted_files': encrypted,
        'unencrypted_files': unencrypted,
        'scan_truncated': truncated,
        'description': description,
        'warning': warning,
    }


def enable_data_protection(runtime_paths, *, backend=None) -> dict:
    """Encrypt existing business data and mark directories for inheritance."""
    if os.name != 'nt' and backend is None:
        raise DataProtectionError('Windows EFS 仅支持 Windows')
    backend = backend or _backend()
    base_dir = Path(runtime_paths.base_dir).resolve()
    if not backend.volume_supports_encryption(base_dir):
        raise DataProtectionError('当前磁盘文件系统不支持 EFS（通常需要 NTFS）')

    roots = _protected_roots(runtime_paths)
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
    candidates = list(_walk_existing(roots))
    candidates.extend(path for path in _sensitive_files(runtime_paths) if path.is_file())
    # Directories first so new/replaced files inherit EFS while migration runs.
    candidates.sort(key=lambda path: (path.is_file(), len(path.parts), str(path).casefold()))
    encrypted = 0
    already_encrypted = 0
    errors = []
    seen = set()
    newly_encrypted = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved != base_dir and base_dir not in resolved.parents:
            errors.append(f'跳过保护范围外路径：{path}')
            continue
        try:
            if backend.is_encrypted(path):
                already_encrypted += 1
                continue
            backend.encrypt(path)
            encrypted += 1
            newly_encrypted.append(path)
        except (DataProtectionError, OSError) as exc:
            errors.append(str(exc))
    rolled_back = 0
    rollback_errors = []
    if errors:
        for path in reversed(newly_encrypted):
            try:
                backend.decrypt(path)
                rolled_back += 1
            except (DataProtectionError, OSError, AttributeError) as exc:
                rollback_errors.append(str(exc))
    return {
        'success': not errors,
        'encrypted': encrypted,
        'already_encrypted': already_encrypted,
        'errors': errors,
        'rolled_back': rolled_back,
        'rollback_errors': rollback_errors,
        'status': data_protection_status(runtime_paths, backend=backend),
    }
