"""Branch-focused tests for split procurement HTTP adapters."""

from __future__ import annotations

import io
from types import SimpleNamespace

from routes import (
    procurement_contract_routes,
    procurement_decision_routes,
    procurement_import_routes,
    procurement_item_supplier_routes,
    procurement_project_routes,
)


def _set_csrf(client):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'procurement-token'


def _post(client, path, data=None, **kwargs):
    payload = dict(data or {})
    payload['csrf_token'] = 'procurement-token'
    return client.post(path, data=payload, **kwargs)


def _stub_render(_template, **_context):
    return 'rendered'


def test_split_project_routes_cover_success_and_failure_paths(
    app,
    client,
    monkeypatch,
):
    module = procurement_project_routes
    monkeypatch.setattr(module, 'render_template', _stub_render)
    service = module.procurement_project_service
    monkeypatch.setattr(
        service,
        'list_projects',
        lambda **_kwargs: {'rows': []},
    )
    monkeypatch.setattr(
        service,
        'project_statuses',
        lambda: {'draft'},
    )
    assert client.get(
        '/procurement/projects?page=bad'
    ).status_code == 200

    monkeypatch.setattr(
        module.historical_price_service,
        'search_prices',
        lambda **_kwargs: [],
    )
    assert client.get(
        '/procurement/history-prices'
    ).status_code == 200
    monkeypatch.setattr(
        module.historical_price_service,
        'price_assistance',
        lambda _query: {'rows': []},
    )
    monkeypatch.setattr(
        module.historical_price_service,
        'negotiation_strategy',
        lambda _query: 'strategy',
    )
    assert client.get(
        '/procurement/history-prices?q=结构件'
    ).status_code == 200

    _set_csrf(client)
    monkeypatch.setattr(
        service,
        'create_project',
        lambda _form: 7,
    )
    assert _post(
        client,
        '/procurement/projects/new',
        {'project_name': '项目'},
    ).status_code == 302
    monkeypatch.setattr(
        service,
        'create_project',
        lambda _form: (_ for _ in ()).throw(
            ValueError('名称错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/new',
        {'project_name': ''},
    ).status_code == 400

    project = {
        'id': 7,
        'budget_minor': 100,
        'target_price_minor': 90,
    }
    monkeypatch.setattr(
        module,
        'project_or_404',
        lambda _project_id: dict(project),
    )
    assert client.get(
        '/procurement/projects/7/edit'
    ).status_code == 200
    monkeypatch.setattr(
        service,
        'update_project',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('更新失败')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/7/edit',
        {'project_name': '坏项目'},
    ).status_code == 400
    monkeypatch.setattr(
        service,
        'update_project',
        lambda *_args: None,
    )
    assert _post(
        client,
        '/procurement/projects/7/edit',
        {'project_name': '好项目'},
    ).status_code == 302

    monkeypatch.setattr(
        service,
        'project_detail',
        lambda _project_id: None,
    )
    assert client.get(
        '/procurement/projects/7'
    ).status_code == 404
    monkeypatch.setattr(
        service,
        'project_detail',
        lambda _project_id: project,
    )
    monkeypatch.setattr(
        service,
        'build_workflow_view',
        lambda _project_id: {},
    )
    assert client.get(
        '/procurement/projects/7'
    ).status_code == 200

    assert _post(
        client,
        '/procurement/projects/7/workflow/jump',
        {'mode': 'enter', 'target_stage': 'items'},
    ).status_code == 302
    monkeypatch.setattr(
        service,
        'jump_to_stage',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('不能跳转')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/7/workflow/jump',
        {'target_stage': 'award'},
    ).status_code == 302
    monkeypatch.setattr(
        service,
        'transition',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('状态错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/7/status',
        {'status': 'bad'},
    ).status_code == 302


def test_split_item_and_supplier_routes_translate_errors(
    app,
    client,
    monkeypatch,
):
    module = procurement_item_supplier_routes
    monkeypatch.setattr(module, 'render_template', _stub_render)
    monkeypatch.setattr(
        module,
        'project_or_404',
        lambda project_id: {'id': project_id},
    )
    service = module.procurement_project_service
    _set_csrf(client)

    monkeypatch.setattr(
        service,
        'add_item',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('明细错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/items',
    ).status_code == 302
    monkeypatch.setattr(service, 'add_item', lambda *_args: 1)
    assert _post(
        client,
        '/procurement/projects/1/items',
    ).status_code == 302

    assert client.get(
        '/procurement/projects/1/items/bulk'
    ).status_code == 200
    monkeypatch.setattr(
        service,
        'add_items_from_paste',
        lambda *_args: None,
    )
    assert _post(
        client,
        '/procurement/projects/1/items/bulk',
        {'pasted_rows': '物资\t1\t件'},
    ).status_code == 302
    monkeypatch.setattr(
        service,
        'add_items_from_paste',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('批量错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/items/bulk',
    ).status_code == 400

    monkeypatch.setattr(
        module.project_document_service,
        'export_project_items',
        lambda _project_id: (_ for _ in ()).throw(
            ValueError('导出错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/items/export',
    ).status_code == 302

    monkeypatch.setattr(
        service,
        'delete_item',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('删除错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/items/2/delete',
    ).status_code == 302

    monkeypatch.setattr(
        service,
        'get_project_item',
        lambda *_args: None,
    )
    assert client.get(
        '/procurement/projects/1/items/2/edit'
    ).status_code == 404
    monkeypatch.setattr(
        service,
        'get_project_item',
        lambda *_args: {'id': 2},
    )
    assert client.get(
        '/procurement/projects/1/items/2/edit'
    ).status_code == 200
    monkeypatch.setattr(
        service,
        'update_item',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('编辑错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/items/2/edit',
    ).status_code == 400

    monkeypatch.setattr(
        service,
        'add_supplier',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('供应商错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/suppliers',
    ).status_code == 302
    assert _post(
        client,
        '/procurement/projects/1/quote-template',
    ).status_code == 302
    monkeypatch.setattr(
        module.quote_service,
        'generate_quote_template',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('模板错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/quote-template',
        {'supplier_id': '2'},
    ).status_code == 302

    monkeypatch.setattr(
        service,
        'delete_supplier',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('删除供应商错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/suppliers/2/delete',
    ).status_code == 302
    monkeypatch.setattr(
        service,
        'get_supplier',
        lambda *_args: None,
    )
    assert client.get(
        '/procurement/projects/1/suppliers/2/edit'
    ).status_code == 404
    monkeypatch.setattr(
        service,
        'get_supplier',
        lambda *_args: {'id': 2},
    )
    monkeypatch.setattr(
        service,
        'update_supplier',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('更新供应商错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/suppliers/2/edit',
    ).status_code == 400


def test_split_import_routes_cover_upload_mapping_and_confirmation(
    app,
    client,
    monkeypatch,
):
    module = procurement_import_routes
    monkeypatch.setattr(module, 'render_template', _stub_render)
    monkeypatch.setattr(
        module,
        'project_or_404',
        lambda project_id: {'id': project_id},
    )
    monkeypatch.setattr(
        module.procurement_project_service,
        'list_suppliers',
        lambda _project_id: [],
    )
    _set_csrf(client)

    assert client.get(
        '/procurement/projects/1/quotes/import'
    ).status_code == 200
    assert _post(
        client,
        '/procurement/projects/1/quotes/import',
    ).status_code == 400
    assert _post(
        client,
        '/procurement/projects/1/quotes/import',
        {'file': (io.BytesIO(b'x'), 'quote.txt')},
        content_type='multipart/form-data',
    ).status_code == 400
    monkeypatch.setattr(
        module.quote_service,
        'create_import_job',
        lambda *_args: 9,
    )
    assert _post(
        client,
        '/procurement/projects/1/quotes/import',
        {
            'supplier_id': '2',
            'file': (io.BytesIO(b'x'), 'quote.xlsx'),
        },
        content_type='multipart/form-data',
    ).status_code == 302

    assert _post(
        client,
        '/procurement/projects/1/quotes/pdf',
    ).status_code == 400
    assert client.get(
        '/procurement/projects/1/quotes/map'
    ).status_code == 200
    assert _post(
        client,
        '/procurement/projects/1/quotes/map',
        {'file': (io.BytesIO(b'x'), 'quote.txt')},
        content_type='multipart/form-data',
    ).status_code == 400
    monkeypatch.setattr(
        module.quote_mapping_service,
        'create_mapping_job',
        lambda *_args: 8,
    )
    assert _post(
        client,
        '/procurement/projects/1/quotes/map',
        {
            'supplier_id': '2',
            'file': (io.BytesIO(b'x'), 'quote.xlsx'),
        },
        content_type='multipart/form-data',
    ).status_code == 302

    monkeypatch.setattr(
        module.quote_mapping_service,
        'get_mapping_job',
        lambda _job_id: None,
    )
    assert client.get(
        '/procurement/quote-mappings/8'
    ).status_code == 404
    mapping_job = {
        'source': {
            'tables': [
                {
                    'name': '报价',
                    'rows': [['名称', '单价']],
                }
            ]
        }
    }
    monkeypatch.setattr(
        module.quote_mapping_service,
        'get_mapping_job',
        lambda _job_id: mapping_job,
    )
    assert client.get(
        '/procurement/quote-mappings/8'
    ).status_code == 200
    monkeypatch.setattr(
        module.quote_mapping_service,
        'map_to_import_job',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('映射错误')
        ),
    )
    assert _post(
        client,
        '/procurement/quote-mappings/8',
    ).status_code == 200
    monkeypatch.setattr(
        module.quote_mapping_service,
        'map_to_import_job',
        lambda *_args: 10,
    )
    assert _post(
        client,
        '/procurement/quote-mappings/8',
    ).status_code == 302

    monkeypatch.setattr(
        module.quote_service,
        'get_import_job',
        lambda _job_id: None,
    )
    assert client.get(
        '/procurement/quote-imports/10'
    ).status_code == 404
    job = {'id': 10, 'project_id': 1}
    monkeypatch.setattr(
        module.quote_service,
        'get_import_job',
        lambda _job_id: job,
    )
    assert client.get(
        '/procurement/quote-imports/10'
    ).status_code == 200
    monkeypatch.setattr(
        module.quote_service,
        'confirm_import',
        lambda _job_id: (_ for _ in ()).throw(
            ValueError('确认错误')
        ),
    )
    assert _post(
        client,
        '/procurement/quote-imports/10/confirm',
    ).status_code == 302


def test_split_decision_routes_cover_error_translation(
    app,
    client,
    monkeypatch,
):
    module = procurement_decision_routes
    monkeypatch.setattr(module, 'render_template', _stub_render)
    monkeypatch.setattr(
        module,
        'project_or_404',
        lambda project_id: {'id': project_id},
    )
    _set_csrf(client)

    monkeypatch.setattr(
        module.comparison_service,
        'comparison_view',
        lambda _project_id: {},
    )
    assert client.get(
        '/procurement/projects/1/comparison'
    ).status_code == 200
    monkeypatch.setattr(
        module.comparison_service,
        'run_configured_comparison',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('规则错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/comparison/run',
    ).status_code == 302
    monkeypatch.setattr(
        module.comparison_service,
        'export_comparison_excel',
        lambda _project_id: (_ for _ in ()).throw(
            ValueError('导出错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/comparison/export',
    ).status_code == 302
    monkeypatch.setattr(
        module.comparison_service,
        'generate_clarifications',
        lambda _project_id: (_ for _ in ()).throw(
            ValueError('澄清错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/clarifications/generate',
    ).status_code == 302
    assert _post(
        client,
        '/procurement/clarifications/1',
        {'project_id': '0'},
    ).status_code == 400
    monkeypatch.setattr(
        module.comparison_service,
        'update_clarification',
        lambda *_args: None,
    )
    assert _post(
        client,
        '/procurement/clarifications/1',
        {'project_id': '1'},
    ).status_code == 302

    monkeypatch.setattr(
        module.award_service,
        'award_view',
        lambda _project_id: {
            'quotes': [],
            'split_rows': [],
            'award': None,
        },
    )
    assert client.get(
        '/procurement/projects/1/award'
    ).status_code == 200
    monkeypatch.setattr(
        module.award_service,
        'create_award',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('成交错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/award',
        {'supplier_id': '2'},
    ).status_code == 400

    monkeypatch.setattr(
        module.negotiation_service,
        'save_round',
        lambda *_args: (_ for _ in ()).throw(
            ValueError('谈判错误')
        ),
    )
    monkeypatch.setattr(
        module.negotiation_service,
        'negotiation_view',
        lambda *_args: {},
    )
    assert _post(
        client,
        '/procurement/projects/1/negotiation',
    ).status_code == 200
    monkeypatch.setattr(
        module.project_document_service,
        'negotiation_plan_defaults',
        lambda _project_id: {
            'plan': {'filename': 'plan.docx'}
        },
    )
    monkeypatch.setattr(
        module.project_document_service,
        'generate_negotiation_plan',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError('预案错误')
        ),
    )
    assert _post(
        client,
        '/procurement/projects/1/negotiation/plan',
    ).status_code == 400


def test_split_contract_routes_persist_only_service_session_id(
    app,
    client,
    monkeypatch,
):
    module = procurement_contract_routes
    monkeypatch.setattr(module, 'render_template', _stub_render)
    monkeypatch.setattr(
        module,
        'project_or_404',
        lambda project_id: {
            'id': project_id,
            'budget_minor': 100,
            'target_price_minor': 90,
        },
    )
    monkeypatch.setattr(
        module.award_service,
        'list_contract_templates',
        lambda: [],
    )
    _set_csrf(client)

    monkeypatch.setattr(
        module.award_service,
        'get_latest_award',
        lambda _project_id: None,
    )
    assert client.get(
        '/procurement/projects/1/to-contract'
    ).status_code == 302
    monkeypatch.setattr(
        module.award_service,
        'get_latest_award',
        lambda _project_id: {'id': 1},
    )
    assert client.get(
        '/procurement/projects/1/to-contract'
    ).status_code == 200
    monkeypatch.setattr(
        module.procurement_contract_handoff_service,
        'create_award_editor_session',
        lambda *_args: SimpleNamespace(session_id='award-sid'),
    )
    assert _post(
        client,
        '/procurement/projects/1/to-contract',
        {'template_filename': 'x.contract-template'},
    ).status_code == 302
    with client.session_transaction() as flask_session:
        assert flask_session['sid'] == 'award-sid'

    assert client.get(
        '/procurement/projects/1/direct-contract'
    ).status_code == 200
    monkeypatch.setattr(
        module.procurement_contract_handoff_service,
        'create_direct_editor_session',
        lambda *_args: SimpleNamespace(session_id='direct-sid'),
    )
    assert _post(
        client,
        '/procurement/projects/1/direct-contract',
        {'template_filename': 'x.contract-template'},
    ).status_code == 302
    with client.session_transaction() as flask_session:
        assert flask_session['sid'] == 'direct-sid'
