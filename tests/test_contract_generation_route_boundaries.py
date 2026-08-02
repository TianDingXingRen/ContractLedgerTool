from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

import template_def
from core.domain_errors import (
    DocumentGenerationError,
    ProcurementLinkError,
    ValidationError,
)
from utils.errors import GENERIC_FILE_ERROR, GENERIC_GENERATE_ERROR
from utils.security import MAX_BATCH_CONTRACTS, MAX_COUNTERPARTY_LENGTH
from utils.session_store import save_session_data


def _set_csrf(client, token='contract-generation-token'):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = token
    return token


def _activate_template(
    app,
    client,
    *,
    fields=None,
    source_docx='',
    session_extra=None,
):
    fields = fields if fields is not None else []
    template = template_def.TemplateDef.create(
        f'合同生成边界测试-{uuid.uuid4().hex[:8]}',
        source_docx,
        fields,
    )
    template_path = template.save()
    sid = uuid.uuid4().hex
    data = {
        'template_name': template.name,
        'template_path': template_path,
        'template_filename': Path(template_path).name,
        'step': 'editor',
        **(session_extra or {}),
    }
    save_session_data(sid, data, app.extensions['runtime_paths'])
    token = _set_csrf(client)
    with client.session_transaction() as flask_session:
        flask_session['sid'] = sid
    return template, token


def _counterparty_field():
    return {
        'id': 0,
        'key': 'party_b',
        'label': '乙方',
        'field_type': 'text',
        'required': True,
    }


def test_generate_redirects_for_missing_or_expired_session(client):
    token = _set_csrf(client)
    missing = client.post('/generate', data={'csrf_token': token})
    assert missing.status_code == 302

    with client.session_transaction() as flask_session:
        flask_session['sid'] = uuid.uuid4().hex
    expired = client.post('/generate', data={'csrf_token': token})
    assert expired.status_code == 302


def test_generate_rejects_missing_template_and_unsafe_source(app, client):
    sid = uuid.uuid4().hex
    paths = app.extensions['runtime_paths']
    save_session_data(sid, {'template_path': 'missing'}, paths)
    token = _set_csrf(client)
    with client.session_transaction() as flask_session:
        flask_session['sid'] = sid
    missing = client.post('/generate', data={'csrf_token': token})
    assert missing.status_code == 400
    assert '未找到模板数据' in missing.get_data(as_text=True)

    _, token = _activate_template(
        app,
        client,
        source_docx='../outside.docx',
    )
    unsafe = client.post('/generate', data={'csrf_token': token})
    assert unsafe.status_code == 400
    assert GENERIC_FILE_ERROR in unsafe.get_data(as_text=True)


@pytest.mark.parametrize(
    ('error', 'expected_status', 'expected_message'),
    [
        (DocumentGenerationError(['broken template']), 500, GENERIC_GENERATE_ERROR),
        (ValidationError('invalid ledger row'), 400, '操作失败'),
        (ProcurementLinkError('link failed'), 500, '操作失败'),
        (RuntimeError('unexpected failure'), 500, '操作失败'),
    ],
)
def test_generate_translates_service_failures(
    app,
    client,
    monkeypatch,
    error,
    expected_status,
    expected_message,
):
    _, token = _activate_template(app, client)
    generation_service = app.extensions['contract_tool'].contract_generation

    def fail_generation(_request):
        raise error

    monkeypatch.setattr(generation_service, 'generate', fail_generation)
    response = client.post('/generate', data={'csrf_token': token})
    assert response.status_code == expected_status
    assert expected_message in response.get_data(as_text=True)


def test_generate_returns_contract_headers(app, client, monkeypatch):
    _, token = _activate_template(app, client)
    generation_service = app.extensions['contract_tool'].contract_generation
    def generate(request):
        Path(request.output_path).write_bytes(b'generated docx')
        return SimpleNamespace(
            contract_id=73,
            output_path=request.output_path,
            previous_project_status=None,
        )

    monkeypatch.setattr(generation_service, 'generate', generate)
    response = client.post('/generate', data={'csrf_token': token})
    try:
        assert response.status_code == 200
        assert response.headers['X-Contract-Id'] == '73'
        assert response.headers['X-Contract-Detail-Url'].endswith('/contracts/73')
    finally:
        response.close()


def test_preflight_rejects_session_template_and_classification_errors(
    app,
    client,
):
    token = _set_csrf(client)
    missing = client.post('/generate/preflight', data={'csrf_token': token})
    assert missing.status_code == 400
    assert '会话已过期' in missing.get_json()['blocking'][0]

    with client.session_transaction() as flask_session:
        flask_session['sid'] = uuid.uuid4().hex
    expired = client.post('/generate/preflight', data={'csrf_token': token})
    assert expired.status_code == 400

    paths = app.extensions['runtime_paths']
    broken_path = paths.templates_dir / 'broken.contract-template'
    broken_path.write_text('{bad json', encoding='utf-8')
    sid = uuid.uuid4().hex
    save_session_data(sid, {'template_path': str(broken_path)}, paths)
    with client.session_transaction() as flask_session:
        flask_session['sid'] = sid
    broken = client.post('/generate/preflight', data={'csrf_token': token})
    assert broken.status_code == 500
    assert '加载模板失败' in broken.get_json()['blocking']

    _, token = _activate_template(app, client)
    invalid = client.post('/generate/preflight', data={
        'csrf_token': token,
        'coverage_start': '1',
    })
    assert invalid.status_code == 400
    assert '合同分类信息无效' in invalid.get_json()['blocking']


@pytest.mark.parametrize(
    ('counterparties', 'expected_message'),
    [
        (
            '\n'.join(f'供应商-{index}' for index in range(MAX_BATCH_CONTRACTS + 1)),
            '批量生成每次不能超过',
        ),
        ('甲' * (MAX_COUNTERPARTY_LENGTH + 1), '对方单位名称不能超过'),
    ],
)
def test_batch_preflight_enforces_counterparty_limits(
    app,
    client,
    counterparties,
    expected_message,
):
    _, token = _activate_template(app, client, fields=[_counterparty_field()])
    response = client.post('/generate/preflight', data={
        'csrf_token': token,
        '_generation_mode': 'batch',
        'batch_counterparties': counterparties,
        'field_0': '',
    })
    assert response.status_code == 400
    assert expected_message in response.get_json()['blocking'][0]


def test_batch_preflight_blocks_procurement_data_sheet(app, client):
    _, token = _activate_template(
        app,
        client,
        fields=[_counterparty_field()],
        session_extra={'procurement_data_sheet_id': 8},
    )
    response = client.post('/generate/preflight', data={
        'csrf_token': token,
        '_generation_mode': 'batch',
        'batch_counterparties': '供应商',
        'field_0': '',
    })
    assert response.status_code == 400
    assert '仅支持单份生成' in response.get_json()['blocking'][0]


def test_batch_route_validates_context_fields_and_counterparties(app, client):
    token = _set_csrf(client)
    no_session = client.post('/generate-batch', data={'csrf_token': token})
    assert no_session.status_code == 400
    assert '会话已过期' in no_session.get_data(as_text=True)

    _, token = _activate_template(
        app,
        client,
        fields=[{
            'id': 0,
            'key': 'memo',
            'label': '备注',
            'field_type': 'text',
        }],
    )
    no_field = client.post('/generate-batch', data={
        'csrf_token': token,
        'field_0': '备注',
        'batch_counterparties': '供应商',
    })
    assert no_field.status_code == 400
    assert '未能识别对方单位字段' in no_field.get_data(as_text=True)

    _, token = _activate_template(app, client, fields=[_counterparty_field()])
    no_counterparty = client.post('/generate-batch', data={
        'csrf_token': token,
        'field_0': '',
    })
    assert no_counterparty.status_code == 400
    assert '请至少输入一个对方单位' in no_counterparty.get_data(as_text=True)
