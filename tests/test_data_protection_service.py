from pathlib import Path
from types import SimpleNamespace

import pytest

from services import data_protection_service as protection


class FakeEfsBackend:
    def __init__(self, *, supported=True, encrypted=None, fail=None):
        self.supported = supported
        self.encrypted = {Path(path).resolve() for path in (encrypted or [])}
        self.fail = {Path(path).resolve() for path in (fail or [])}
        self.calls = []

    def volume_supports_encryption(self, _path):
        return self.supported

    def is_encrypted(self, path):
        return Path(path).resolve() in self.encrypted

    def encrypt(self, path):
        resolved = Path(path).resolve()
        self.calls.append(resolved)
        if resolved in self.fail:
            raise protection.DataProtectionError(f'cannot encrypt {resolved.name}')
        self.encrypted.add(resolved)

    def decrypt(self, path):
        self.encrypted.discard(Path(path).resolve())


def _runtime_paths(tmp_path):
    paths = SimpleNamespace(
        base_dir=tmp_path,
        data_dir=tmp_path / 'data',
        templates_dir=tmp_path / 'templates',
        uploads_dir=tmp_path / 'uploads',
        output_dir=tmp_path / 'output',
        sessions_dir=tmp_path / 'sessions',
        config_file=tmp_path / 'config.json',
    )
    for name in ('data', 'templates', 'uploads', 'output', 'sessions'):
        (tmp_path / name).mkdir()
    (paths.data_dir / 'contracts.db').write_bytes(b'sqlite')
    (paths.output_dir / 'contract.docx').write_bytes(b'docx')
    (paths.config_file).write_text('{}', encoding='utf-8')
    (tmp_path / '.secret_key').write_text('secret', encoding='utf-8')
    return paths


def test_status_reports_unsupported_volume(tmp_path):
    status = protection.data_protection_status(
        _runtime_paths(tmp_path), backend=FakeEfsBackend(supported=False),
    )
    assert status['supported'] is False
    assert status['enabled'] is False


def test_enable_encrypts_roots_existing_files_and_sensitive_files(tmp_path):
    paths = _runtime_paths(tmp_path)
    backend = FakeEfsBackend()
    report = protection.enable_data_protection(paths, backend=backend)
    assert report['success'] is True
    assert report['status']['enabled'] is True
    assert paths.data_dir.resolve() in backend.encrypted
    assert (paths.data_dir / 'contracts.db').resolve() in backend.encrypted
    assert paths.config_file.resolve() in backend.encrypted
    assert (tmp_path / '.secret_key').resolve() in backend.encrypted
    first_file = next(index for index, path in enumerate(backend.calls) if path.is_file())
    assert all(path.is_dir() for path in backend.calls[:first_file])


def test_enable_is_idempotent_and_reports_partial_failures(tmp_path):
    paths = _runtime_paths(tmp_path)
    database = (paths.data_dir / 'contracts.db').resolve()
    backend = FakeEfsBackend(encrypted=[paths.data_dir], fail=[database])
    report = protection.enable_data_protection(paths, backend=backend)
    assert report['success'] is False
    assert report['already_encrypted'] >= 1
    assert any('contracts.db' in error for error in report['errors'])
    assert report['rolled_back'] > 0
    assert report['rollback_errors'] == []
    assert report['status']['partial'] is True


def test_enable_rejects_unsupported_volume(tmp_path):
    with pytest.raises(protection.DataProtectionError, match='NTFS'):
        protection.enable_data_protection(
            _runtime_paths(tmp_path), backend=FakeEfsBackend(supported=False),
        )


def test_status_reports_backend_probe_failure(tmp_path):
    class FailingBackend(FakeEfsBackend):
        def volume_supports_encryption(self, _path):
            raise protection.DataProtectionError('probe failed')

    status = protection.data_protection_status(_runtime_paths(tmp_path), backend=FailingBackend())
    assert status['supported'] is False
    assert 'probe failed' in status['description']
