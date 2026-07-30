from pathlib import Path

import pytest

from routes import procurement_document_routes as document_routes


def _set_csrf(client):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'document-token'


@pytest.mark.parametrize(
    ('url', 'service', 'extension', 'payload'),
    [
        ('/procurement/projects/1/quote-template/2', 'generate_quote_template', '.xlsx', b'xlsx'),
        ('/procurement/projects/1/inquiry', 'generate_inquiry_letter', '.docx', b'docx'),
        ('/procurement/projects/1/award/document', 'generate_award_recommendation', '.docx', b'docx'),
        ('/procurement/projects/1/erp-oa-summary', 'generate_erp_oa_summary', '.xlsx', b'xlsx'),
        ('/procurement/projects/1/archive', 'generate_project_archive', '.zip', b'zip'),
    ],
)
def test_generated_document_routes_download_files(
    app, client, tmp_path, monkeypatch, url, service, extension, payload,
):
    output = tmp_path / f'generated{extension}'
    output.write_bytes(payload)
    target_module = (
        document_routes.quote_service
        if service == 'generate_quote_template'
        else document_routes.project_document_service
    )
    monkeypatch.setattr(target_module, service, lambda *_args: str(output))
    _set_csrf(client)

    response = client.post(url, data={'csrf_token': 'document-token'})

    assert response.status_code == 200
    assert response.data == payload
    assert 'attachment' in response.headers['Content-Disposition']
    assert client.get(url).status_code == 405


def test_clarification_document_forwards_supplier_filter(app, client, tmp_path, monkeypatch):
    output = tmp_path / 'clarification.docx'
    output.write_bytes(b'clarification')
    captured = []
    monkeypatch.setattr(
        document_routes.project_document_service,
        'generate_clarification_letter',
        lambda project_id, supplier_id: captured.append((project_id, supplier_id)) or str(output),
    )
    _set_csrf(client)
    response = client.post(
        '/procurement/projects/7/clarifications/document',
        data={'csrf_token': 'document-token', 'supplier_id': '9'},
    )
    assert response.status_code == 200
    assert captured == [(7, 9)]


@pytest.mark.parametrize(
    ('url', 'service'),
    [
        ('/procurement/projects/1/quote-template/2', 'generate_quote_template'),
        ('/procurement/projects/1/inquiry', 'generate_inquiry_letter'),
        ('/procurement/projects/1/clarifications/document', 'generate_clarification_letter'),
        ('/procurement/projects/1/award/document', 'generate_award_recommendation'),
        ('/procurement/projects/1/erp-oa-summary', 'generate_erp_oa_summary'),
        ('/procurement/projects/1/archive', 'generate_project_archive'),
    ],
)
def test_generated_document_routes_redirect_on_service_error(
    app, client, monkeypatch, url, service,
):
    target_module = (
        document_routes.quote_service
        if service == 'generate_quote_template'
        else document_routes.project_document_service
    )
    monkeypatch.setattr(
        target_module, service,
        lambda *_args: (_ for _ in ()).throw(ValueError('invalid project state')),
    )
    _set_csrf(client)
    response = client.post(url, data={'csrf_token': 'document-token'})
    assert response.status_code == 302
    assert 'error=' in response.headers['Location']


def test_project_file_download_validates_record_and_path(app, client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        document_routes.procurement_file_service,
        'resolve_download',
        lambda _file_id: (_ for _ in ()).throw(
            FileNotFoundError('项目文件不存在')
        ),
    )
    assert client.get('/procurement/files/1/download').status_code == 404

    monkeypatch.setattr(
        document_routes.procurement_file_service,
        'resolve_download',
        lambda _path: (_ for _ in ()).throw(ValueError('unsafe path')),
    )
    assert client.get('/procurement/files/1/download').status_code == 400

    monkeypatch.setattr(
        document_routes.procurement_file_service,
        'resolve_download',
        lambda _file_id: (_ for _ in ()).throw(
            FileNotFoundError('项目文件已丢失')
        ),
    )
    assert client.get('/procurement/files/1/download').status_code == 404

    existing = tmp_path / 'stored.docx'
    existing.write_bytes(b'stored document')
    monkeypatch.setattr(
        document_routes.procurement_file_service,
        'resolve_download',
        lambda _file_id: {
            'path': Path(existing),
            'download_name': '原始文件.docx',
        },
    )
    response = client.get('/procurement/files/1/download')
    assert response.status_code == 200
    assert response.data == b'stored document'
    assert 'attachment' in response.headers['Content-Disposition']
