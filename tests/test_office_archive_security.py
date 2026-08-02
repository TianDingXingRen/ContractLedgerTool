import os
import random
import zipfile

import pytest

from utils.security import validate_office_archive


def _write_zip(path, members):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)


def test_small_office_archive_is_accepted(tmp_path):
    path = tmp_path / 'safe.xlsx'
    _write_zip(path, [('[Content_Types].xml', b'<Types/>'), ('xl/workbook.xml', b'<workbook/>')])

    validate_office_archive(path)


@pytest.mark.parametrize('member_name', ['../escape.xml', '/absolute.xml', 'C:/drive.xml'])
def test_office_archive_rejects_unsafe_member_paths(tmp_path, member_name):
    path = tmp_path / 'unsafe.xlsx'
    _write_zip(path, [(member_name, b'payload')])

    with pytest.raises(ValueError, match='不安全的内部路径'):
        validate_office_archive(path)


def test_office_archive_rejects_extreme_compression_ratio(tmp_path):
    path = tmp_path / 'bomb.docx'
    _write_zip(path, [('word/document.xml', b'A' * (2 * 1024 * 1024))])

    with pytest.raises(ValueError, match='压缩比异常'):
        validate_office_archive(path)


def test_office_archive_rejects_duplicate_paths_and_missing_package_parts(tmp_path):
    duplicate = tmp_path / 'duplicate.docx'
    with pytest.warns(UserWarning, match='Duplicate name'):
        _write_zip(duplicate, [
            ('[Content_Types].xml', b'<Types/>'),
            ('word/document.xml', b'<document/>'),
            ('word/document.xml', b'<document/>'),
        ])
    with pytest.raises(ValueError, match='重复'):
        validate_office_archive(duplicate)

    missing = tmp_path / 'missing.docx'
    _write_zip(missing, [('[Content_Types].xml', b'<Types/>')])
    with pytest.raises(ValueError, match='必要的内部结构'):
        validate_office_archive(missing)


def test_random_non_zip_payloads_fail_with_controlled_error(tmp_path):
    rng = random.Random(20260720)
    path = tmp_path / 'fuzz.xlsx'
    for size in range(1, 257, 17):
        path.write_bytes(rng.randbytes(size) if hasattr(rng, 'randbytes') else os.urandom(size))
        with pytest.raises(ValueError, match='Office 文件结构无效'):
            validate_office_archive(path)
