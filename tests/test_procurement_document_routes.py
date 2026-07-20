from pathlib import Path

import pytest

from routes import procurement_document_routes as document_routes


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

    response = client.get(url)

    assert response.status_code == 200
    assert response.data == payload
    assert 'attachment' in response.headers['Content-Disposition']


def test_clarification_document_forwards_supplier_filter(app, client, tmp_path, monkeypatch):
    output = tmp_path / 'clarification.docx'
    output.write_bytes(b'clarification')
    captured = []
    monkeypatch.setattr(
        document_routes.project_document_service,
        'generate_clarification_letter',
        lambda project_id, supplier_id: captured.append((project_id, supplier_id)) or str(output),
    )
    response = client.get('/procurement/projects/7/clarifications/document?supplier_id=9')
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
    response = client.get(url)
    assert response.status_code == 302
    assert 'error=' in response.headers['Location']


def test_project_file_download_validates_record_and_path(app, client, tmp_path, monkeypatch):
    monkeypatch.setattr(document_routes.procurement_store, 'get_project_file', lambda _file_id: None)
    assert client.get('/procurement/files/1/download').status_code == 404

    record = {'relative_path': 'project/file.docx', 'original_name': '原始文件.docx'}
    monkeypatch.setattr(document_routes.procurement_store, 'get_project_file', lambda _file_id: record)
    monkeypatch.setattr(
        document_routes.procurement_file_service, 'absolute_path',
        lambda _path: (_ for _ in ()).throw(ValueError('unsafe path')),
    )
    assert client.get('/procurement/files/1/download').status_code == 400

    missing = tmp_path / 'missing.docx'
    monkeypatch.setattr(document_routes.procurement_file_service, 'absolute_path', lambda _path: missing)
    assert client.get('/procurement/files/1/download').status_code == 404

    existing = tmp_path / 'stored.docx'
    existing.write_bytes(b'stored document')
    monkeypatch.setattr(document_routes.procurement_file_service, 'absolute_path', lambda _path: Path(existing))
    response = client.get('/procurement/files/1/download')
    assert response.status_code == 200
    assert response.data == b'stored document'
    assert 'attachment' in response.headers['Content-Disposition']
