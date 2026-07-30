import base64
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from openpyxl import Workbook
from werkzeug.datastructures import FileStorage

from config import config as app_config
from config import Config
from ledger_store.schema import CURRENT_SCHEMA_VERSION as LEDGER_SCHEMA_VERSION
from procurement_store.schema import (
    CURRENT_SCHEMA_VERSION as PROCUREMENT_SCHEMA_VERSION,
)
from services import handover_archive, handover_service, procurement_project_service


def _csrf(client):
    with client.session_transaction() as session:
        session['_csrf_token'] = 'upload-security-token'
    return 'upload-security-token'


def test_template_upload_rejects_unsafe_archive_without_residual_file(app, client):
    uploads = app.extensions['runtime_paths'].uploads_dir
    before = {path.name for path in uploads.iterdir()}
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('../escape.xml', b'x')
        archive.writestr('[Content_Types].xml', b'<Types/>')
        archive.writestr('word/document.xml', b'<document/>')
    payload.seek(0)

    response = client.post(
        '/template/upload-style',
        data={'csrf_token': _csrf(client), 'file': (payload, 'unsafe.docx')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    assert {path.name for path in uploads.iterdir()} == before


def test_full_backup_rejects_extreme_compression_ratio(tmp_path, monkeypatch):
    database = tmp_path / 'contracts.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE sample(value TEXT)')
    database_bytes = database.read_bytes()
    expanded = b'0' * (2 * 1024 * 1024)
    records = [
        {
            'path': 'data/contracts.db', 'size': len(database_bytes),
            'sha256': hashlib.sha256(database_bytes).hexdigest(),
        },
        {
            'path': 'output/expanded.bin', 'size': len(expanded),
            'sha256': hashlib.sha256(expanded).hexdigest(),
        },
    ]
    manifest = {
        'package_type': handover_service.PACKAGE_TYPE,
        'manifest_version': 1,
        'files': records,
    }
    package = tmp_path / 'compressed.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('data/contracts.db', database_bytes)
        archive.writestr('output/expanded.bin', expanded)
        archive.writestr(
            handover_service.MANIFEST_NAME,
            json.dumps(manifest).encode('utf-8'),
        )
    monkeypatch.setattr(handover_service, '_package_dir', lambda: str(tmp_path))

    with pytest.raises(ValueError, match='压缩比异常'):
        handover_service.validate_full_backup_package(package)


def test_empty_sqlite_file_is_not_accepted_as_application_backup(tmp_path):
    database = tmp_path / 'empty.db'
    with sqlite3.connect(database):
        pass

    with pytest.raises(ValueError, match='缺少应用表'):
        handover_archive.validate_application_database(
            database,
            max_ledger_version=LEDGER_SCHEMA_VERSION,
            max_procurement_version=PROCUREMENT_SCHEMA_VERSION,
        )


def test_config_clamps_zero_rate_limits_and_rejects_wildcard_hosts(tmp_path):
    (tmp_path / 'config.json').write_text(
        json.dumps({
            'TRUSTED_HOSTS': ['*', 'contracts.internal'],
            'RATE_LIMIT_DEFAULT': [0, 0],
            'RATE_LIMIT_GLOBAL': [-1, 0],
            'RATE_LIMITS': {'/generate': [0, 0]},
        }),
        encoding='utf-8',
    )

    loaded = Config(tmp_path)

    assert loaded.RATE_LIMIT_DEFAULT == (1, 1)
    assert loaded.RATE_LIMIT_GLOBAL == (1, 1)
    assert loaded.RATE_LIMITS['/generate'] == (1, 1)
    assert '*' not in loaded.TRUSTED_HOSTS
    assert 'contracts.internal' in loaded.TRUSTED_HOSTS


def test_procurement_excel_import_enforces_row_limit():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['物资名称', '规格', '图号', '数量', '单位'])
    for index in range(procurement_project_service.MAX_PROCUREMENT_IMPORT_ROWS + 1):
        sheet.append([f'物资{index}', '', '', 1, '件'])
    payload = io.BytesIO()
    workbook.save(payload)
    workbook.close()
    payload.seek(0)
    storage = FileStorage(stream=payload, filename='items.xlsx')

    with pytest.raises(ValueError, match='一次最多导入'):
        procurement_project_service.add_items_from_excel(1, storage)


def test_non_loopback_requests_require_remote_token(app, client, monkeypatch):
    monkeypatch.setattr(app_config, 'REMOTE_ACCESS_TOKEN', '0123456789abcdef')
    remote = {'REMOTE_ADDR': '192.168.10.20'}
    denied = client.get('/', environ_overrides=remote)
    assert denied.status_code == 401
    credentials = base64.b64encode(b'user:0123456789abcdef').decode('ascii')
    allowed = client.get(
        '/', environ_overrides=remote,
        headers={'Authorization': f'Basic {credentials}'},
    )
    assert allowed.status_code == 200


def test_untrusted_host_header_is_rejected_before_routing(client):
    response = client.get('/', headers={'Host': 'attacker.example'})
    assert response.status_code == 400
