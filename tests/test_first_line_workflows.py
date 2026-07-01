from datetime import date, timedelta
import os
import uuid

import ledger_store
import template_def
from utils import helpers


def _set_csrf(client, token='first-line-token'):
    with client.session_transaction() as session:
        session['_csrf_token'] = token
    return token


def test_payment_work_view_and_quick_update(app, client):
    contract_id, plan_count = ledger_store.create_contract_with_plans(
        {
            'contract_no': 'PAY-WORK-001',
            'title': '付款处理测试合同',
            'counterparty': '测试供应商',
            'owner': '经办人甲',
        },
        {},
        'payment-work.docx',
        [{
            'phase_name': '到货款',
            'confirm_status': 'pending',
            'payment_status': 'unpaid',
            'due_date': date.today().strftime('%Y-%m-%d'),
            'due_amount': 1000,
            'paid_amount': 0,
            'confidence': 'medium',
        }],
    )
    assert plan_count == 1
    plan = ledger_store.list_payment_plans(contract_id=contract_id)[0]

    page = client.get('/payment-plans')
    html = page.get_data(as_text=True)
    assert '处理视图' in html
    assert '批量确认' in html
    assert '导出当前筛选' in html

    token = _set_csrf(client)
    response = client.post(
        f'/payment-plans/{plan["id"]}/quick-update',
        data={
            'csrf_token': token,
            'action': 'partial',
            'paid_amount': '400',
            'paid_date': date.today().strftime('%Y-%m-%d'),
            'view': 'work',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    updated = ledger_store.get_payment_plan(plan['id'])
    assert updated['confirm_status'] == 'confirmed'
    assert updated['payment_status'] == 'partial'
    assert updated['paid_amount'] == 400


def test_generate_preflight_blocks_duplicate_contract_no(app, client):
    ledger_store.create_contract(
        {'contract_no': 'HT-DUP-001', 'title': '已有合同'},
        {},
        'existing.docx',
    )
    fields = [{
        'id': 0,
        'key': 'contract_no',
        'label': '合同编号',
        'field_type': 'text',
        'required': True,
        'location': {'type': 'paragraph', 'body_index': 0},
    }]
    tpl = template_def.TemplateDef.create('复核测试模板', '', fields)
    template_path = tpl.save()
    sid = uuid.uuid4().hex
    helpers.save_session_data(sid, {
        'template_name': tpl.name,
        'template_path': template_path,
        'template_filename': os.path.basename(template_path),
        'fields': fields,
        'step': 'editor',
    })
    token = _set_csrf(client)
    with client.session_transaction() as session:
        session['sid'] = sid

    response = client.post('/generate/preflight', data={
        'csrf_token': token,
        'field_0': 'HT-DUP-001',
    })
    payload = response.get_json()
    assert response.status_code == 400
    assert payload['ok'] is False
    assert any('已存在' in item for item in payload['blocking'])


def test_index_renders_workbench_todos(app, client):
    ledger_store.create_contract_with_plans(
        {
            'contract_no': 'TODO-PAY-001',
            'title': '首页待办付款合同',
            'counterparty': '测试供应商',
            'owner': '经办人乙',
        },
        {},
        'todo.docx',
        [{
            'phase_name': '尾款',
            'confirm_status': 'confirmed',
            'payment_status': 'unpaid',
            'due_date': (date.today() - timedelta(days=1)).strftime('%Y-%m-%d'),
            'due_amount': 3200,
            'paid_amount': 0,
            'confidence': 'high',
        }],
    )
    response = client.get('/')
    html = response.get_data(as_text=True)
    assert 'data-testid="workbench-todos"' in html
    assert '付款已逾期' in html
    assert '首页待办付款合同' in html


def test_contract_ledger_separates_list_and_project_views(app, client):
    ledger_store.create_contract(
        {
            'contract_no': 'PROJ-001',
            'title': '项目进度测试合同',
            'status': 'signed',
            'project_name': '一线改造项目',
            'coverage_start': 1,
            'coverage_end': 12,
        },
        {},
        'project-ledger.docx',
    )

    list_page = client.get('/contracts')
    list_html = list_page.get_data(as_text=True)
    assert list_page.status_code == 200
    assert 'data-testid="contract-list-view"' in list_html
    assert 'data-testid="project-progress-view"' not in list_html
    assert '合同列表' in list_html
    assert '项目进度' in list_html

    project_page = client.get('/contracts?view=project')
    project_html = project_page.get_data(as_text=True)
    assert project_page.status_code == 200
    assert 'data-testid="project-progress-view"' in project_html
    assert 'data-testid="contract-list-view"' not in project_html
    assert '一线改造项目' in project_html
