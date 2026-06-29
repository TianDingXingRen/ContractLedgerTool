import io
import json
import os
import uuid
from datetime import date

from openpyxl import load_workbook
from docx import Document
from docx.oxml.ns import qn
from werkzeug.datastructures import FileStorage

import ledger_store
import procurement_store
import template_def
from services import (
    award_service, comparison_service, procurement_project_service,
    procurement_file_service, project_document_service, quote_service,
)
from utils import helpers


def _non_empty_runs(document):
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            if run.text.strip():
                yield run
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if run.text.strip():
                            yield run


def _assert_docx_uses_fangsong(document):
    style_fonts = document.styles['Normal']._element.rPr.rFonts
    assert style_fonts.get(qn('w:eastAsia')) == '仿宋'
    for run in _non_empty_runs(document):
        r_pr = run._element.rPr
        assert r_pr is not None
        assert r_pr.rFonts.get(qn('w:eastAsia')) == '仿宋'


def _project_with_items_and_suppliers():
    project_id = procurement_project_service.create_project({
        'project_no': 'CG-TEST-0001',
        'project_name': '结构件加工竞争性谈判',
        'purchase_method': 'competitive_negotiation',
        'demand_department': '研发部',
        'owner': '采购员甲',
        'budget_amount': '10000',
        'target_price': '9000',
        'delivery_place': '北京',
        'delivery_requirement': '30天',
        'payment_requirement': '验收后30天付款',
    })
    procurement_project_service.add_item(project_id, {
        'item_name': '结构件A', 'spec_model': 'A-01', 'drawing_no': 'T-A',
        'quantity': '10', 'unit': '件', 'required_delivery_date': '2026-08-01',
    })
    procurement_project_service.add_item(project_id, {
        'item_name': '结构件B', 'spec_model': 'B-02', 'drawing_no': 'T-B',
        'quantity': '5', 'unit': '件', 'required_delivery_date': '2026-08-10',
    })
    suppliers = []
    for name in ('供应商A', '供应商B', '供应商C'):
        suppliers.append(procurement_project_service.add_supplier(project_id, {
            'supplier_name': name, 'contact_person': name[-1] + '联系人',
        }))
    return project_id, suppliers


def _filled_quote_file(project_id, supplier_id, prices, quote_round=1, missing_last=False):
    path = quote_service.generate_quote_template(project_id, supplier_id)
    workbook = load_workbook(path)
    info = workbook['报价信息']
    info['B5'] = quote_round
    info['B6'] = '2026-06-23'
    info['B7'] = '2026-07-23'
    info['B10'] = '30天'
    info['B11'] = '验收后30天付款'
    detail = workbook['报价明细']
    detail['H2'] = prices[0]
    detail['H3'] = prices[1]
    if missing_last:
        detail.delete_rows(3, 1)
    total = 10 * prices[0] + (0 if missing_last else 5 * prices[1])
    info['B16'] = total
    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return FileStorage(stream=stream, filename=f'quote-{supplier_id}.xlsx')


def _import_quote(project_id, supplier_id, prices, missing_last=False, quote_round=1):
    file_storage = _filled_quote_file(
        project_id, supplier_id, prices, quote_round=quote_round, missing_last=missing_last
    )
    job_id = quote_service.create_import_job(project_id, supplier_id, quote_round, file_storage)
    job = procurement_store.get_import_job(job_id)
    assert job['errors'] == []
    quote_id = quote_service.confirm_import(job_id)
    assert quote_id
    return quote_id, job


def test_multi_round_quote_uses_latest_confirmed_round(app):
    project_id, suppliers = _project_with_items_and_suppliers()
    first_quote, _ = _import_quote(project_id, suppliers[0], [100, 200], quote_round=1)
    second_quote, second_job = _import_quote(project_id, suppliers[0], [90, 180], quote_round=2)
    assert quote_service.confirm_import(second_job['id']) == second_quote
    latest = procurement_store.get_latest_quotes(project_id)
    assert len(latest) == 1
    assert latest[0]['id'] == second_quote
    assert latest[0]['quote_round'] == 2
    assert latest[0]['total_amount_minor'] < procurement_store.get_quote(first_quote)['total_amount_minor']


def test_procurement_schema_crud_and_constraints(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    project = procurement_project_service.project_detail(project_id)
    assert project['project_no'] == 'CG-TEST-0001'
    assert project['budget_minor'] == 1_000_000
    assert len(project['items']) == 2
    assert len(project['suppliers']) == 3
    assert client.get(f'/procurement/projects/{project_id}').status_code == 200
    assert client.get(
        f'/procurement/projects/{project_id}/items/{project["items"][0]["id"]}/edit'
    ).status_code == 200
    assert client.get(
        f'/procurement/projects/{project_id}/suppliers/{suppliers[0]}/edit'
    ).status_code == 200

    try:
        procurement_project_service.create_project({
            'project_no': 'CG-TEST-0001', 'project_name': '重复项目',
        })
        assert False, '重复项目编号应被拒绝'
    except Exception:
        pass

    procurement_project_service.transition(project_id, 'documents_ready')
    assert procurement_store.get_project(project_id)['status'] == 'documents_ready'
    try:
        procurement_project_service.transition(project_id, 'contract_created')
        assert False, '非法状态跳转应被拒绝'
    except ValueError as exc:
        message = str(exc)
        assert '询价文件已准备' in message
        assert '合同已生成' in message
        assert 'documents_ready' not in message
        assert 'contract_created' not in message

    procurement_store.delete_project_supplier(project_id, suppliers[-1])
    assert len(procurement_store.list_project_suppliers(project_id)) == 2


def test_inline_item_and_supplier_add_return_to_entry_sections(app, client):
    project_id = procurement_project_service.create_project({
        'project_no': 'CG-TEST-ANCHOR',
        'project_name': '连续录入跳转测试',
    })
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'inline-token'

    item_response = client.post(
        f'/procurement/projects/{project_id}/items',
        data={
            'csrf_token': 'inline-token',
            'item_name': '测试物资',
            'quantity': '2',
            'unit': '件',
        },
        follow_redirects=False,
    )
    assert item_response.status_code == 302
    assert item_response.headers['Location'].endswith(f'/procurement/projects/{project_id}#items')

    supplier_response = client.post(
        f'/procurement/projects/{project_id}/suppliers',
        data={
            'csrf_token': 'inline-token',
            'supplier_name': '连续录入供应商',
        },
        follow_redirects=False,
    )
    assert supplier_response.status_code == 302
    assert supplier_response.headers['Location'].endswith(f'/procurement/projects/{project_id}#suppliers')


def test_standard_quote_import_page_downloads_supplier_template(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    page = client.get(f'/procurement/projects/{project_id}/quotes/import')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert '下载标准报价模板' in html
    assert f'/procurement/projects/{project_id}/quote-template' in html

    response = client.get(
        f'/procurement/projects/{project_id}/quote-template?supplier_id={suppliers[0]}'
    )
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response.close()


def test_quote_import_comparison_clarification_and_award(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    _import_quote(project_id, suppliers[0], [100, 200])
    _, missing_job = _import_quote(project_id, suppliers[1], [130, 210], missing_last=True)
    _import_quote(project_id, suppliers[2], [70, 190])
    assert missing_job['warnings']
    preview = client.get(f'/procurement/quote-imports/{missing_job["id"]}')
    assert preview.status_code == 200
    preview_html = preview.get_data(as_text=True)
    assert '已导入' in preview_html
    assert '>confirmed<' not in preview_html

    run_id = comparison_service.run_comparison(project_id, 20)
    assert run_id
    comparison = procurement_store.get_latest_comparison(project_id)
    result_types = {row['result_type'] for row in comparison['results']}
    assert 'missing_item' in result_types
    assert 'high_price' in result_types
    assert 'low_price' in result_types
    assert client.get(f'/procurement/projects/{project_id}/comparison').status_code == 200

    created = comparison_service.generate_clarifications(project_id)
    assert created > 0
    questions = procurement_store.list_clarifications(project_id)
    assert any(row['question_type'] == 'missing_item' for row in questions)
    clarification_path = project_document_service.generate_clarification_letter(project_id)
    assert '报价澄清问题清单' in '\n'.join(p.text for p in Document(clarification_path).paragraphs)

    try:
        award_service.create_award(project_id, suppliers[0], {
            'reason_summary': '未说明为何不选最低价',
        })
        assert False, '非最低有效价必须填写原因'
    except ValueError as exc:
        assert '最低总价' in str(exc)

    recommendation_id = award_service.create_award(project_id, suppliers[2], {
        'reason_summary': '价格合理且技术响应完整',
        'price_reason': '总价最低',
    })
    assert recommendation_id
    award = procurement_store.get_latest_award(project_id)
    assert award['supplier_id'] == suppliers[2]
    assert client.get(f'/procurement/projects/{project_id}/award').status_code == 200
    award_path = project_document_service.generate_award_recommendation(project_id)
    assert '成交建议' in '\n'.join(p.text for p in Document(award_path).paragraphs)
    sheet = award_service.build_contract_data_sheet(project_id)
    payload = json.loads(sheet['payload_json'])
    assert payload['supplier']['name'] == '供应商C'
    assert len(payload['items']) == 2
    file_types = {row['file_type'] for row in procurement_store.list_project_files(project_id)}
    assert {'quote_template', 'supplier_quote', 'clarification', 'award'} <= file_types


def test_inquiry_document_contains_project_items(app):
    project_id, _ = _project_with_items_and_suppliers()
    path = project_document_service.generate_inquiry_letter(project_id)
    document = Document(path)
    all_text = '\n'.join(
        [paragraph.text for paragraph in document.paragraphs]
        + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    )
    assert '询价函' in all_text
    assert '结构件A' in all_text
    assert '结构件B' in all_text
    _assert_docx_uses_fangsong(document)
    assert procurement_store.get_project(project_id)['status'] == 'documents_ready'


def test_negotiation_plan_prefills_generates_word_and_archives(app, client):
    project_id, _ = _project_with_items_and_suppliers()
    page = client.get(f'/procurement/projects/{project_id}/negotiation/plan')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert '谈判预案' in html
    assert '结构件A' in html
    assert '目标价格' in html

    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'plan-token'
    response = client.post(
        f'/procurement/projects/{project_id}/negotiation/plan',
        data={
            'csrf_token': 'plan-token',
            'project_background': '按附件模板生成，减少重复填写。',
            'fixed_asset': '否',
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    response.close()

    files = [
        row for row in procurement_store.list_project_files(project_id)
        if row['file_type'] == 'negotiation_plan'
    ]
    assert files
    path = procurement_file_service.absolute_path(files[-1]['relative_path'])
    document = Document(path)
    all_text = '\n'.join(
        [paragraph.text for paragraph in document.paragraphs]
        + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    )
    assert '结构件加工竞争性谈判谈判预案' in all_text
    assert '按附件模板生成，减少重复填写。' in all_text
    assert '结构件A' in all_text
    assert '评价方案' in all_text
    _assert_docx_uses_fangsong(document)


def test_procurement_to_contract_prefills_editor_and_links_ledger(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    _import_quote(project_id, suppliers[0], [100, 200])
    award_service.create_award(project_id, suppliers[0], {
        'reason_summary': '综合评审通过',
    })
    assert client.get(f'/procurement/projects/{project_id}/to-contract').status_code == 200

    fields = [
        {'id': 0, 'key': 'project_name', 'label': '项目名称', 'field_type': 'text',
         'required': True, 'location': {'type': 'paragraph', 'body_index': 0}},
        {'id': 1, 'key': 'supplier', 'label': '供应商名称', 'field_type': 'text',
         'required': True, 'location': {'type': 'paragraph', 'body_index': 1}},
        {'id': 2, 'key': 'amount', 'label': '合同金额', 'field_type': 'number',
         'required': True, 'decimal_places': 2, 'location': {'type': 'paragraph', 'body_index': 2}},
    ]
    tpl = template_def.TemplateDef.create('采购转合同测试模板', '', fields)
    template_path = tpl.save()
    data = award_service.prepare_editor_session(project_id, os.path.basename(template_path))
    assert data['fields'][0]['default_value'] == '结构件加工竞争性谈判'
    assert data['fields'][1]['default_value'] == '供应商A'
    assert data['project_name'] == '结构件加工竞争性谈判'

    sid = uuid.uuid4().hex
    helpers.save_session_data(sid, data)
    with client.session_transaction() as flask_session:
        flask_session['sid'] = sid
        flask_session['_csrf_token'] = 'procurement-token'
    editor_page = client.get('/editor')
    assert editor_page.status_code == 200
    editor_html = editor_page.get_data(as_text=True)
    assert 'value="供应商A"' in editor_html
    assert 'value="结构件加工竞争性谈判"' in editor_html

    response = client.post('/generate', data={
        'csrf_token': 'procurement-token',
        'project_name': '结构件加工竞争性谈判',
        'field_0': '结构件加工竞争性谈判',
        'field_1': '供应商A',
        'field_2': '2000.00',
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    contract_id = int(response.headers['X-Contract-Id'])
    response.close()
    links = procurement_store.get_project_contract_links(project_id)
    assert links[0]['contract_id'] == contract_id
    assert procurement_store.get_project(project_id)['status'] == 'contract_created'
    assert ledger_store.get_contract(contract_id)['counterparty'] == '供应商A'


def test_workflow_jump_records_skipped_stages(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'jump-token'
    response = client.post(
        f'/procurement/projects/{project_id}/workflow/jump',
        data={
            'csrf_token': 'jump-token',
            'target_stage': 'negotiation',
            'note': '项目已线下询价，直接补录谈判',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers['Location'].endswith(f'/procurement/projects/{project_id}/negotiation')
    assert procurement_store.get_project(project_id)['status'] == 'negotiating'
    events = procurement_store.list_project_audit_events(project_id, actions=['workflow_jump'])
    assert events
    assert events[0]['after']['target_stage'] == 'negotiation'
    assert 'quotes' in events[0]['after']['skipped_stages']


def test_direct_contract_session_and_generated_contract_ref(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    fields = [
        {'id': 0, 'key': 'project_name', 'label': '项目名称', 'field_type': 'text',
         'required': True, 'location': {'type': 'paragraph', 'body_index': 0}},
        {'id': 1, 'key': 'supplier', 'label': '供应商名称', 'field_type': 'text',
         'required': True, 'location': {'type': 'paragraph', 'body_index': 1}},
    ]
    tpl = template_def.TemplateDef.create('直接合同测试模板', '', fields)
    template_path = tpl.save()

    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'direct-token'
    response = client.post(
        f'/procurement/projects/{project_id}/direct-contract',
        data={'csrf_token': 'direct-token', 'template_filename': os.path.basename(template_path)},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/editor')

    editor_page = client.get('/editor')
    editor_html = editor_page.get_data(as_text=True)
    assert 'value="结构件加工竞争性谈判"' in editor_html
    assert 'value="供应商A"' in editor_html

    response = client.post('/generate', data={
        'csrf_token': 'direct-token',
        'project_name': '结构件加工竞争性谈判',
        'field_0': '结构件加工竞争性谈判',
        'field_1': '供应商A',
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    contract_id = int(response.headers['X-Contract-Id'])
    response.close()
    links = procurement_store.get_project_contract_links(project_id)
    assert any(row['contract_id'] == contract_id and row['source_type'] == 'direct_contract' for row in links)


def test_negotiation_can_start_without_quotes(app, client):
    project_id, suppliers = _project_with_items_and_suppliers()
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'negotiation-token'
    page = client.get(f'/procurement/projects/{project_id}/negotiation')
    html = page.get_data(as_text=True)
    assert '无报价，可手工录入' in html
    response = client.post(
        f'/procurement/projects/{project_id}/negotiation',
        data={
            'csrf_token': 'negotiation-token',
            'round_no': '1',
            'meeting_date': '2026-06-25',
            'summary': '直接进入谈判',
            f'amount_{suppliers[0]}': '8800.50',
            f'delivery_{suppliers[0]}': '20天',
            f'payment_{suppliers[0]}': '验收后付款',
            f'commitment_{suppliers[0]}': '按期交付',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    rounds = procurement_store.list_negotiation_rounds(project_id)
    assert rounds[0]['commitments'][0]['quote_amount_minor'] == 880050
    minutes_path = project_document_service.generate_negotiation_minutes(project_id)
    minutes = Document(minutes_path)
    minutes_text = '\n'.join(
        [paragraph.text for paragraph in minutes.paragraphs]
        + [cell.text for table in minutes.tables for row in table.rows for cell in row.cells]
    )
    assert '谈判人员签字' in minutes_text
    assert '供应商代表' in minutes_text
    _assert_docx_uses_fangsong(minutes)


def test_payment_due_soon_crosses_month_boundary(app, client, monkeypatch):
    import routes.payments_bp as payments_bp

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 25)

    monkeypatch.setattr(payments_bp, 'date', FixedDate)
    contract_id = ledger_store.create_contract_with_plans(
        {'contract_no': 'PAY-CROSS-001', 'title': '跨月付款测试'}, {}, 'cross.docx',
        [{
            'phase_name': '到货款',
            'confirm_status': 'confirmed',
            'payment_status': 'unpaid',
            'due_date': '2026-07-01',
            'due_amount': 1000,
            'paid_amount': 0,
        }],
    )
    assert contract_id
    response = client.get('/payment-plans')
    html = response.get_data(as_text=True)
    assert '2026-07-01' in html
    assert '即将到期' in html


def test_procurement_routes_render_and_reject_missing_csrf(app, client):
    response = client.get('/procurement', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/procurement/projects')

    response = client.get('/procurement/projects')
    assert response.status_code == 200
    assert '采购前置工作台' in response.get_data(as_text=True)
    assert client.get('/procurement/history-prices').status_code == 200
    assert client.get('/procurement/projects/new').status_code == 200
    project_id, _ = _project_with_items_and_suppliers()
    detail = client.get(f'/procurement/projects/{project_id}')
    assert detail.status_code == 200
    detail_html = detail.get_data(as_text=True)
    assert 'data-testid="procurement-workflow"' in detail_html
    assert '直接生成合同' in detail_html
    assert '谈判预案' in detail_html
    list_html = client.get('/procurement/projects').get_data(as_text=True)
    assert '竞争性谈判' in list_html
    assert 'competitive_negotiation' not in list_html
    assert client.get(f'/procurement/projects/{project_id}/quotes/import').status_code == 200
    response = client.post('/procurement/projects/new', data={'project_name': '无令牌'})
    assert response.status_code == 400


def test_procurement_schema_is_idempotent_and_preserves_contracts(app):
    contract_id = ledger_store.create_contract(
        {'contract_no': 'PROC-MIG-001', 'title': '迁移保护测试'}, {}, 'migration.docx'
    )
    procurement_store.init_db()
    procurement_store.init_db()
    assert ledger_store.get_contract(contract_id)['contract_no'] == 'PROC-MIG-001'
    with ledger_store.get_conn() as conn:
        version = conn.execute('SELECT MAX(version) FROM procurement_schema_version').fetchone()[0]
    assert version == 3
