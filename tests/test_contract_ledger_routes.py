"""Branch coverage for the split contract editor and ledger routes."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from routes import contract_editor_routes, contract_ledger_routes
from services import contract_editor_service, contract_ledger_service
from utils.security import MAX_BATCH_CONTRACTS


def _post(client, path, data=None):
    token = 'contract-ledger-route-token'
    with client.session_transaction() as session:
        session['_csrf_token'] = token
    form = dict(data or {})
    form['csrf_token'] = token
    return client.post(path, data=form)


def _ledger_model(**overrides):
    model = {
        'contracts': [],
        'contract_ids': [],
        'project_groups': [],
        'view_mode': 'list',
        'q': '',
        'status': '',
        'page': 1,
        'pages': 1,
        'total': 0,
    }
    model.update(overrides)
    return model


def test_contract_ledger_normalizes_view_and_page(
    app,
    monkeypatch,
):
    captured = {}

    def fake_ledger_view(**kwargs):
        captured.update(kwargs)
        return _ledger_model()

    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'ledger_view',
        fake_ledger_view,
    )
    monkeypatch.setattr(
        contract_ledger_routes,
        'render_template',
        lambda _name, **model: model,
    )

    response = app.test_client().get(
        '/contracts?q=Acme&status=active&view=bad&page=bad'
    )

    assert response.status_code == 200
    assert captured == {
        'query': 'Acme',
        'status': 'active',
        'view_mode': 'list',
        'page': 1,
    }


def test_contract_export_streams_service_artifact(
    app,
    tmp_path,
    monkeypatch,
):
    artifact = tmp_path / 'ledger.xlsx'
    artifact.write_bytes(b'ledger-export')
    captured = {}

    def fake_export(output_dir, **kwargs):
        captured['output_dir'] = output_dir
        captured.update(kwargs)
        return str(artifact), '合同台账_20260729.xlsx'

    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'export_ledger',
        fake_export,
    )

    response = _post(
        app.test_client(),
        '/contracts/export',
        {'q': 'A', 'status': 'signed'},
    )

    assert response.status_code == 200
    assert response.get_data() == b'ledger-export'
    assert captured['query'] == 'A'
    assert captured['status'] == 'signed'
    disposition = response.headers['Content-Disposition']
    assert "filename*=UTF-8''" in disposition
    assert '_20260729.xlsx' in disposition


@pytest.mark.parametrize(
    ('path', 'data', 'message'),
    [
        (
            '/contracts/batch-delete',
            {'ids': 'not-json'},
            '无效的 ID 列表',
        ),
        (
            '/contracts/batch-delete',
            {'ids': '"123"'},
            '无效的 ID 列表',
        ),
        (
            '/contracts/batch-delete',
            {'ids': '[0]'},
            '无效的 ID 列表',
        ),
        (
            '/contracts/batch-delete',
            {
                'ids': json.dumps(
                    list(range(1, MAX_BATCH_CONTRACTS + 2))
                )
            },
            f'单次不能超过 {MAX_BATCH_CONTRACTS} 条记录',
        ),
        (
            '/contracts/batch-status',
            {'ids': '[]', 'status': 'forged'},
            '无效的状态值',
        ),
        (
            '/contracts/batch-status',
            {'ids': 'not-json', 'status': 'active'},
            '无效的 ID 列表',
        ),
        (
            '/contracts/batch-status',
            {
                'ids': json.dumps(
                    list(range(1, MAX_BATCH_CONTRACTS + 2))
                ),
                'status': 'active',
            },
            f'单次不能超过 {MAX_BATCH_CONTRACTS} 条记录',
        ),
    ],
)
def test_contract_batch_routes_reject_invalid_input(
    app,
    path,
    data,
    message,
):
    response = _post(app.test_client(), path, data)
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)


def test_contract_batch_routes_delegate_valid_commands(
    app,
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'batch_delete',
        lambda contract_ids: captured.setdefault(
            'deleted',
            contract_ids,
        )
        and len(contract_ids),
    )
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'batch_update_status',
        lambda contract_ids, status: captured.update(
            {'updated': contract_ids, 'status': status}
        )
        or len(contract_ids),
    )

    delete_response = _post(
        app.test_client(),
        '/contracts/batch-delete',
        {'ids': '[1, 2]'},
    )
    status_response = _post(
        app.test_client(),
        '/contracts/batch-status',
        {'ids': '[3]', 'status': 'active'},
    )

    assert delete_response.status_code == 302
    assert status_response.status_code == 302
    assert captured == {
        'deleted': [1, 2],
        'updated': [3],
        'status': 'active',
    }


def test_contract_trash_uses_positive_page(app, monkeypatch):
    captured = []
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'trash_view',
        lambda page: captured.append(page)
        or _ledger_model(trash_mode=True),
    )
    monkeypatch.setattr(
        contract_ledger_routes,
        'render_template',
        lambda _name, **model: model,
    )

    response = app.test_client().get('/contracts/trash?page=-4')

    assert response.status_code == 200
    assert captured == [1]


@pytest.mark.parametrize(
    ('path', 'service_name', 'message'),
    [
        (
            '/contracts/91/soft-delete',
            'soft_delete',
            '合同不存在或已在回收站中',
        ),
        (
            '/contracts/91/restore',
            'restore',
            '合同不在回收站中',
        ),
        (
            '/contracts/91/permanent-delete',
            'permanently_delete',
            '合同不在回收站中或无法删除',
        ),
    ],
)
def test_contract_lifecycle_routes_report_missing_state(
    app,
    monkeypatch,
    path,
    service_name,
    message,
):
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        service_name,
        lambda _contract_id: 0,
    )

    response = _post(app.test_client(), path)

    assert response.status_code == 404
    assert message in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ('path', 'service_name'),
    [
        ('/contracts/91/soft-delete', 'soft_delete'),
        ('/contracts/91/restore', 'restore'),
        (
            '/contracts/91/permanent-delete',
            'permanently_delete',
        ),
    ],
)
def test_contract_lifecycle_routes_redirect_after_success(
    app,
    monkeypatch,
    path,
    service_name,
):
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        service_name,
        lambda _contract_id: 1,
    )

    response = _post(app.test_client(), path)

    assert response.status_code == 302


def test_contract_permanent_delete_preserves_conflict_reason(
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'permanently_delete',
        lambda _contract_id: (_ for _ in ()).throw(
            ValueError('仍有关联付款')
        ),
    )

    response = _post(
        app.test_client(),
        '/contracts/91/permanent-delete',
    )

    assert response.status_code == 302
    assert '/contracts/91' in response.headers['Location']
    assert 'error=' in response.headers['Location']


def test_contract_update_rejects_missing_invalid_and_bad_form(
    app,
    monkeypatch,
):
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'contract_exists',
        lambda _contract_id: False,
    )
    missing = _post(
        app.test_client(),
        '/contracts/8/update',
        {'status': 'active'},
    )
    assert missing.status_code == 404

    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'contract_exists',
        lambda _contract_id: True,
    )
    invalid = _post(
        app.test_client(),
        '/contracts/8/update',
        {'status': 'forged'},
    )
    assert invalid.status_code == 400

    monkeypatch.setattr(
        contract_ledger_routes.contract_batch_support,
        'parse_contract_update',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('金额格式无效')
        ),
    )
    bad_form = _post(
        app.test_client(),
        '/contracts/8/update',
        {'status': 'active'},
    )
    assert bad_form.status_code == 400
    assert '金额格式无效' not in bad_form.get_data(as_text=True)


def test_contract_update_delegates_and_preserves_return_location(
    app,
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'contract_exists',
        lambda _contract_id: True,
    )
    monkeypatch.setattr(
        contract_ledger_routes.contract_batch_support,
        'parse_contract_update',
        lambda _form, status: {'status': status},
    )
    monkeypatch.setattr(
        contract_ledger_routes.contract_ledger_service,
        'update_contract',
        lambda contract_id, update, *, expected_revision: captured.update(
            {
                'contract_id': contract_id,
                'update': update,
                'expected_revision': expected_revision,
            }
        ),
    )

    response = _post(
        app.test_client(),
        '/contracts/8/update',
        {
            'status': 'active',
            'revision': '7',
            'return_tab': 'payments',
            'return_page': '2',
        },
    )

    assert response.status_code == 302
    assert captured == {
        'contract_id': 8,
        'update': {'status': 'active'},
        'expected_revision': 7,
    }
    assert 'tab=payments' in response.headers['Location']
    assert 'page=2' in response.headers['Location']


def test_contract_update_rejects_stale_revision_and_preserves_submitted_form(app):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {
            'contract_no': 'CAS-001',
            'title': '原始标题',
            'owner': '原负责人',
            'coverage_not_applicable': True,
        },
        {},
        '',
    )
    baseline = ledger_store.get_contract(contract_id)
    common = {
        'contract_no': 'CAS-001',
        'counterparty': '',
        'amount': '',
        'sign_date': '',
        'expiry_date': '',
        'status': 'draft',
        'project_name': '',
        'subsystem_name': '',
        'coverage_mode': 'not_applicable',
        'revision': str(baseline['revision']),
    }

    winner = _post(
        app.test_client(),
        f'/contracts/{contract_id}/update',
        {**common, 'title': '先保存的标题', 'owner': '原负责人'},
    )
    assert winner.status_code == 302

    stale = _post(
        app.test_client(),
        f'/contracts/{contract_id}/update',
        {**common, 'title': '旧页面标题', 'owner': '后保存的负责人'},
    )
    html = stale.get_data(as_text=True)
    current = ledger_store.get_contract(contract_id)

    assert stale.status_code == 409
    assert current['title'] == '先保存的标题'
    assert current['owner'] == '原负责人'
    assert current['revision'] == baseline['revision'] + 1
    assert '旧页面标题' in html
    assert '后保存的负责人' in html
    assert '合同已被其他页面修改' in html
    assert f'name="revision" value="{current["revision"]}"' in html


def test_contract_update_requires_revision_baseline(app):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {
            'title': '需要版本',
            'coverage_not_applicable': True,
        },
        {},
        '',
    )
    response = _post(
        app.test_client(),
        f'/contracts/{contract_id}/update',
        {
            'title': '不应保存',
            'status': 'draft',
            'coverage_mode': 'not_applicable',
        },
    )

    assert response.status_code == 400
    assert ledger_store.get_contract(contract_id)['title'] == '需要版本'


def test_contract_editor_redirects_expired_session(
    app,
    monkeypatch,
):
    client = app.test_client()
    with client.session_transaction() as session:
        session['sid'] = 'expired'
    monkeypatch.setattr(
        contract_editor_routes,
        'load_session_data',
        lambda *_args: (_ for _ in ()).throw(
            FileNotFoundError
        ),
    )

    response = client.get('/editor')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_contract_editor_redirects_without_session(app):
    response = app.test_client().get('/editor')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_contract_editor_renders_service_model(app, monkeypatch):
    client = app.test_client()
    with client.session_transaction() as session:
        session['sid'] = 'valid'
    monkeypatch.setattr(
        contract_editor_routes,
        'load_session_data',
        lambda *_args: {'template_name': '测试模板'},
    )
    monkeypatch.setattr(
        contract_editor_routes.contract_editor_service,
        'build_editor_model',
        lambda *_args: {'template_name': '测试模板'},
    )
    monkeypatch.setattr(
        contract_editor_routes,
        'render_template',
        lambda _name, **model: model,
    )

    response = client.get('/editor')

    assert response.status_code == 200
    model = response.get_json()
    assert model['template_name'] == '测试模板'
    assert len(model['draft_page_id']) == 32
    assert model['draft_page_id'].isalnum()


def test_contract_home_renders_dashboard_snapshot(app, monkeypatch):
    monkeypatch.setattr(
        contract_editor_routes.dashboard_service,
        'build_dashboard_snapshot',
        lambda: {'contract_stats': {'total': 3}},
    )
    monkeypatch.setattr(
        contract_editor_routes,
        'render_template',
        lambda _name, **model: model,
    )

    response = app.test_client().get('/?autostart_error=failed')

    assert response.status_code == 200
    model = response.get_json()
    assert model['contract_stats'] == {'total': 3}
    assert model['autostart_error'] == 'failed'


def test_contract_editor_service_recovers_legacy_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        contract_editor_service,
        'template_path_from_session',
        lambda *_args: None,
    )
    monkeypatch.setattr(
        contract_editor_service,
        'editor_preview_model',
        lambda *_args: {
            'blocks': [{'type': 'paragraph'}],
            'warnings': ['preview-warning'],
        },
    )
    monkeypatch.setattr(
        contract_editor_service.ledger_store,
        'list_project_names',
        lambda: ['项目A'],
    )
    data = {
        'fields': [{'key': 'party_a'}],
        'template_name': '旧模板',
    }

    model = contract_editor_service.build_editor_model(data, object())

    assert model['fields'][0]['id'] == 0
    assert model['preview_blocks'] == [{'type': 'paragraph'}]
    assert model['preview_warnings'] == ['preview-warning']
    assert model['project_names'] == ['项目A']
    assert model['batch_allowed'] is True
    assert len(model['template_revision']) == 64
    assert model['draft_scope'] == 'template::'


def test_contract_editor_service_normalizes_duplicate_and_string_field_ids(
    monkeypatch,
):
    monkeypatch.setattr(
        contract_editor_service,
        'template_path_from_session',
        lambda *_args: None,
    )
    monkeypatch.setattr(
        contract_editor_service,
        'editor_preview_model',
        lambda *_args: {'blocks': [], 'warnings': []},
    )
    monkeypatch.setattr(
        contract_editor_service.ledger_store,
        'list_project_names',
        lambda: [],
    )
    data = {
        'fields': [
            {'id': '7', 'key': 'first'},
            {'id': 7, 'key': 'duplicate'},
            {'id': 'not-a-number', 'key': 'invalid'},
        ],
    }

    model = contract_editor_service.build_editor_model(data, object())

    assert [field['id'] for field in model['fields']] == [7, 0, 1]
    assert all(
        isinstance(field['id'], int) and field['id'] >= 0
        for field in model['fields']
    )


def test_editor_draft_revision_tracks_template_content(tmp_path):
    template_path = tmp_path / 'sales.contract-template'
    template_path.write_text('{"name":"版本一"}', encoding='utf-8')

    first = contract_editor_service.build_draft_revision(
        template_path,
        [{'id': 1, 'key': 'amount'}],
    )
    template_path.write_text('{"name":"版本二"}', encoding='utf-8')
    second = contract_editor_service.build_draft_revision(
        template_path,
        [{'id': 1, 'key': 'amount'}],
    )

    assert len(first) == 64
    assert len(second) == 64
    assert first != second


def test_editor_draft_scope_isolates_procurement_sources():
    award_scope = contract_editor_service.build_draft_scope({
        'source_type': 'award',
        'source_project_id': 7,
        'procurement_data_sheet_id': 11,
    })
    another_sheet = contract_editor_service.build_draft_scope({
        'source_type': 'award',
        'source_project_id': 7,
        'procurement_data_sheet_id': 12,
    })
    direct_scope = contract_editor_service.build_draft_scope({
        'source_type': 'direct_contract',
        'source_project_id': 7,
    })

    assert award_scope == 'award:7:11'
    assert len({award_scope, another_sheet, direct_scope}) == 3


def test_contract_ledger_service_queries_project_view(monkeypatch):
    monkeypatch.setattr(
        contract_ledger_service.ledger_store,
        'list_contracts',
        lambda **_kwargs: {
            'rows': [{'id': 4}],
            'page': 1,
            'pages': 1,
            'total': 1,
        },
    )
    monkeypatch.setattr(
        contract_ledger_service.ledger_store,
        'list_project_grouped_contracts',
        lambda **_kwargs: [{'project_name': '项目A'}],
    )

    model = contract_ledger_service.ledger_view(
        query='A',
        status='active',
        view_mode='project',
        page=1,
    )

    assert model['contract_ids'] == [4]
    assert model['project_groups'] == [{'project_name': '项目A'}]


def test_contract_ledger_service_trash_export_and_commands(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        contract_ledger_service.ledger_store,
        'list_contracts',
        lambda **kwargs: {
            'rows': [{'id': 7}],
            'page': kwargs['page'],
            'pages': 2,
            'total': 1,
        },
    )
    trash = contract_ledger_service.trash_view(page=2)
    assert trash['contract_ids'] == [7]
    assert trash['page'] == 2
    assert trash['trash_mode'] is True

    rows = iter([{'id': 7}])
    monkeypatch.setattr(
        contract_ledger_service.ledger_store,
        'iter_contracts',
        lambda **_kwargs: rows,
    )
    exported = {}

    def fake_export(path, contracts, **kwargs):
        exported['path'] = path
        exported['contracts'] = list(contracts)
        exported.update(kwargs)

    monkeypatch.setattr(
        contract_ledger_service.xlsx_exporter,
        'export_contracts',
        fake_export,
    )
    output_path, download_name = (
        contract_ledger_service.export_ledger(
            tmp_path,
            query='A',
            status='active',
            today=date(2026, 7, 29),
        )
    )
    assert output_path.startswith(str(tmp_path))
    assert output_path.endswith('.xlsx')
    assert download_name == '合同台账_20260729.xlsx'
    assert exported['contracts'] == [{'id': 7}]
    assert exported['title'] == '合同台账'
    assert exported['streaming'] is True

    monkeypatch.setattr(
        contract_ledger_service.ledger_store,
        'get_contract',
        lambda contract_id: {'id': contract_id},
    )
    assert contract_ledger_service.contract_exists(7) is True

    command_names = {
        'update_contract': 'update_contract',
        'batch_delete_contracts': 'batch_delete',
        'batch_update_status': 'batch_status',
        'soft_delete_contract': 'soft_delete',
        'restore_contract': 'restore',
        'permanently_delete_contract': 'permanent_delete',
    }
    for store_name, marker in command_names.items():
        monkeypatch.setattr(
            contract_ledger_service.ledger_store,
            store_name,
            lambda *_args, marker=marker, **_kwargs: marker,
        )

    assert contract_ledger_service.update_contract(
        7,
        {'status': 'active'},
        expected_revision=3,
    ) == 'update_contract'
    assert contract_ledger_service.batch_delete([7]) == 'batch_delete'
    assert contract_ledger_service.batch_update_status(
        [7],
        'active',
    ) == 'batch_status'
    assert contract_ledger_service.soft_delete(7) == 'soft_delete'
    assert contract_ledger_service.restore(7) == 'restore'
    assert (
        contract_ledger_service.permanently_delete(7)
        == 'permanent_delete'
    )


def test_contract_editor_service_loads_template_source(
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        contract_editor_service,
        'template_path_from_session',
        lambda *_args: 'template.contract-template',
    )
    monkeypatch.setattr(
        contract_editor_service.template_def.TemplateDef,
        'load',
        lambda _path: SimpleNamespace(
            data={'source_docx': 'source.docx'}
        ),
    )
    monkeypatch.setattr(
        contract_editor_service,
        'editor_preview_model',
        lambda source, *_args: captured.setdefault(
            'source',
            source,
        )
        and {'blocks': [], 'warnings': []},
    )
    monkeypatch.setattr(
        contract_editor_service.ledger_store,
        'list_project_names',
        lambda: [],
    )

    contract_editor_service.build_editor_model({}, object())

    assert captured['source'] == 'source.docx'


def test_contract_editor_service_contains_template_load_failure(
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        contract_editor_service,
        'template_path_from_session',
        lambda *_args: 'broken.contract-template',
    )
    monkeypatch.setattr(
        contract_editor_service.template_def.TemplateDef,
        'load',
        lambda _path: (_ for _ in ()).throw(
            ValueError('broken template')
        ),
    )

    def fake_preview(source, *_args):
        captured['source'] = source
        return {'blocks': [], 'warnings': []}

    monkeypatch.setattr(
        contract_editor_service,
        'editor_preview_model',
        fake_preview,
    )
    monkeypatch.setattr(
        contract_editor_service.ledger_store,
        'list_project_names',
        lambda: [],
    )

    contract_editor_service.build_editor_model({}, object())

    assert captured['source'] == ''
