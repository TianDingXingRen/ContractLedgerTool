"""全功能回归测试 — 生成测试数据并逐项验证所有功能"""
import io
import json
import os
import sys
import tempfile
import uuid
import zipfile

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

import template_def

PASS = 0
FAIL = 0
_results = []

def _docx_text(blob):
    from docx import Document
    doc = Document(io.BytesIO(blob))
    return '\n'.join(p.text or '' for p in doc.paragraphs)

def check(label, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        _results.append(f'  [PASS] {label}')
    else:
        FAIL += 1
        _results.append(f'  [FAIL] {label}  -  {detail}')

def section(title):
    _results.append(f'\n── {title} ──')

def summary():
    print('\n' + '=' * 60)
    for r in _results:
        print(r)
    print('=' * 60)
    print(f' 通过 {PASS} / 失败 {FAIL}  （共 {PASS + FAIL}）')
    return FAIL

# ═══════════════════════════════════════════════════════
def _run_with_app(flask_app):
    client = flask_app.test_client()
    CSRF = 'test-full-functional-csrf'

    def set_csrf(sess, token=None):
        sess['_csrf_token'] = token or CSRF

    def get(path, **kw):
        return client.get(path, **kw)

    def post(path, data=None, csrf=True, **kw):
        if data is None:
            data = {}
        if csrf and 'csrf_token' not in data:
            data['csrf_token'] = CSRF
        return client.post(path, data=data, **kw)

    def with_session(fn):
        with client.session_transaction() as sess:
            set_csrf(sess)
            fn(sess)

    # ── 1. 首页 ──
    section('1. 首页仪表盘')
    r = get('/')
    check('首页返回 200', r.status_code == 200, f'status={r.status_code}')
    r.close()

    # ── 2. 模板列表 ──
    section('2. 模板列表')
    r = get('/templates')
    check('模板列表 200', r.status_code == 200)
    html = r.get_data(as_text=True); r.close()
    check('模板列表含模板名称', 'test' in html and 'Template1_Test' in html)

    # ── 3. 编制模板页面 ──
    section('3. 编制模板页面')
    r = get('/create-template')
    check('编制模板页面 200', r.status_code == 200)
    html = r.get_data(as_text=True); r.close()
    check('编制模板页面含标题', '编制模板' in html)

    # ── 4. 手动创建模板 (无源docx) ──
    section('4. 手动创建模板')
    tpl_name = f'全功能测试模板_{uuid.uuid4().hex[:6]}'
    form = {
        'template_name': tpl_name,
        'stored_name': '',
        'field_label_0': '甲方名称',
        'field_key_0': 'party_a',
        'field_type_0': 'text',
        'field_required_0': 'on',
        'field_label_1': '合同金额',
        'field_key_1': 'amount_field',
        'field_type_1': 'text',
        'field_label_2': '乙方名称',
        'field_key_2': 'party_b',
        'field_type_2': 'text',
        'field_label_3': '签约日期',
        'field_key_3': 'sign_date_field',
        'field_type_3': 'text',
    }
    with client.session_transaction() as sess:
        set_csrf(sess)
    r = post('/template/manual-save', data=form)
    check('模板创建重定向 302', r.status_code == 302, str(r.status_code))
    r.close()

    with client.session_transaction() as sess:
        sid = sess.get('sid')
    check('session 已设置 sid', bool(sid), str(sid))

    # 从 session 获取模板文件名
    from utils import helpers
    sdata = helpers.load_session_data(sid)
    tpl_filename = sdata.get('template_filename', '')
    check('session 含 template_filename', bool(tpl_filename))

    # ── 5. 模板编辑器页面 ──
    section('5. 模板编辑器')
    r = get(f'/template/{tpl_filename}')
    check('编辑器页面 200', r.status_code == 200)
    r.close()

    # ── 6. 保存模板默认值 ──
    section('6. 保存模板默认值')
    defaults = {
        'field_0': '测试甲方有限公司',
        'field_1': '500000',
        'field_2': '测试乙方公司',
        'field_3': '2026-03-15',
    }
    with client.session_transaction() as sess:
        set_csrf(sess)
        sess['sid'] = sid
    r = post('/template-defaults', data=defaults)
    resp = r.get_json(); r.close()
    check('默认值保存成功', resp.get('success') is True, resp.get('message', ''))

    # ── 7. 进入编辑器并生成单份合同 ──
    section('7. 生成单份合同')
    with client.session_transaction() as sess:
        set_csrf(sess)
        sess['sid'] = sid
    gen_form = {
        'coverage_mode': 'not_applicable',
        'field_0': '测试甲方有限公司',
        'field_1': '500000',
        'field_2': '深圳市测试乙方科技有限公司',
        'field_3': '2026-03-15',
    }
    r = post('/generate', data=gen_form)
    check('合同生成 200', r.status_code == 200, f'status={r.status_code}')
    docx_body = r.get_data()
    r.close()
    check('生成的 docx 非空', len(docx_body) > 1000)
    docx_text = _docx_text(docx_body)
    check('文档含甲方名称', '测试甲方有限公司' in docx_text)
    check('文档含乙方名称', '深圳市测试乙方科技有限公司' in docx_text)

    # ── 8. 批量生成 ──
    section('8. 批量生成合同')
    with client.session_transaction() as sess:
        set_csrf(sess)
        sess['sid'] = sid
    batch_form = {k: v for k, v in gen_form.items()}
    batch_form['batch_counterparties'] = '北京客户A\n上海客户B\n广州客户C'
    batch_form['batch_field_key'] = 'party_b'
    r = post('/generate-batch', data=batch_form)
    check('批量生成 200', r.status_code == 200, f'status={r.status_code}')
    zip_body = r.get_data(); r.close()
    check('ZIP 文件非空', len(zip_body) > 500)
    with zipfile.ZipFile(io.BytesIO(zip_body)) as zf:
        names = zf.namelist()
        check('ZIP 含 3 份合同', len(names) == 3, str(names))
        check('ZIP 命名含客户', any('北京客户A' in n for n in names))

    # ── 9. 合同台账列表 ──
    section('9. 合同台账')
    r = get('/contracts')
    check('合同台账 200', r.status_code == 200)
    html = r.get_data(as_text=True); r.close()
    check('台账含北京客户A', '北京客户A' in html)
    check('台账含上海客户B', '上海客户B' in html)

    # 搜索
    r = get('/contracts?q=北京客户A')
    html = r.get_data(as_text=True); r.close()
    check('搜索返回结果', '北京客户A' in html)

    # 按状态筛选
    r = get('/contracts?status=draft')
    check('按状态筛选 200', r.status_code == 200)
    r.close()

    # ── 10. 合同详情 ──
    section('10. 合同详情与更新')
    # 获取最新合同 ID
    import ledger_store
    result = ledger_store.list_contracts(per_page=100)
    contracts = result.get('rows', [])
    check('有合同记录', len(contracts) > 0, f'共 {len(contracts)} 条')

    if contracts:
        cid = contracts[0]['id']

        # 10a. 查看详情
        r = get(f'/contracts/{cid}')
        check('合同详情 200', r.status_code == 200)
        r.close()

        # 10b. 更新合同
        with client.session_transaction() as sess:
            set_csrf(sess)
        update_form = {
            'contract_no': f'HT-{uuid.uuid4().hex[:8]}',
            'title': '更新后合同标题',
            'counterparty': '更新后对方单位',
            'amount': '888888',
            'sign_date': '2026-05-01',
            'owner': '测试负责人',
            'status': 'active',
        }
        r = post(f'/contracts/{cid}/update', data=update_form)
        check('合同更新重定向', r.status_code == 302)
        r.close()

        # 验证更新
        updated = ledger_store.get_contract(cid)
        check('合同标题已更新', updated.get('title') == '更新后合同标题')
        check('合同状态已更新', updated.get('status') == 'active')
        check('合同金额已更新', updated.get('amount') == 888888.0)

        # 10c. 下载合同 docx
        r = get(f'/contracts/{cid}/download')
        check('合同下载 200', r.status_code == 200)
        r.close()

    # ── 11. 付款计划管理 ──
    section('11. 付款计划')
    if contracts:
        cid = contracts[0]['id']

        # 11a. 添加付款计划
        with client.session_transaction() as sess:
            set_csrf(sess)
        plan_form = {
            'plan_count': '2',
            'plan_0_phase_name': '预付款',
            'plan_0_payment_type': 'conditional',
            'plan_0_trigger_event': '合同签订',
            'plan_0_trigger_days': '30',
            'plan_0_due_date': '2026-04-15',
            'plan_0_ratio': '30',
            'plan_0_due_amount': '266666.4',
            'plan_0_confidence': 'high',
            'plan_0_condition_text': '合同生效后30个工作日内支付',
            'plan_0_source_text': '合同签订后支付30%预付款',
            'plan_0_remark': '测试备注1',
            'plan_1_phase_name': '验收款',
            'plan_1_payment_type': 'conditional',
            'plan_1_trigger_event': '验收合格',
            'plan_1_trigger_days': '15',
            'plan_1_due_date': '2026-07-15',
            'plan_1_ratio': '70',
            'plan_1_due_amount': '622221.6',
            'plan_1_confidence': 'medium',
            'plan_1_condition_text': '验收合格后15个工作日内支付',
            'plan_1_source_text': '验收后支付70%尾款',
            'plan_1_remark': '测试备注2',
        }
        r = post(f'/contracts/{cid}/payments/save', data=plan_form)
        check('付款计划保存重定向', r.status_code == 302)
        r.close()

        # 验证保存
        plans = ledger_store.list_payment_plans(contract_id=cid)
        check('付款计划已创建', len(plans) >= 2, f'共 {len(plans)} 条')
        if plans:
            check('计划含预付款', any(p.get('phase_name') == '预付款' for p in plans))
            check('计划含验收款', any(p.get('phase_name') == '验收款' for p in plans))
            check('预付款置信度 high', any(p.get('confidence') == 'high' and p.get('phase_name') == '预付款' for p in plans))

            # 11b. 一键确认
            with client.session_transaction() as sess:
                set_csrf(sess)
            r = post(f'/contracts/{cid}/payments/confirm-all')
            check('一键确认重定向', r.status_code == 302)
            r.close()

    # ── 12. 付款计划列表 ──
    section('12. 付款计划列表')
    r = get('/payment-plans')
    check('付款计划列表 200', r.status_code == 200)
    r.close()

    r = get('/payment-plans?confirm_status=confirmed')
    check('筛选已确认 200', r.status_code == 200)
    r.close()

    r = get('/payment-plans?start_date=2026-01-01&end_date=2026-12-31')
    check('按日期筛选 200', r.status_code == 200)
    r.close()

    # ── 13. 付款计划导出 ──
    section('13. 付款计划导出')
    with client.session_transaction() as sess:
        set_csrf(sess)
    r = post('/payment-plans/export-next-month')
    check('导出下月付款计划 200', r.status_code == 200)
    r.close()

    # ── 14. 合同导出 ──
    section('14. 合同台账导出')
    with client.session_transaction() as sess:
        set_csrf(sess)
    r = post('/contracts/export')
    check('导出合同台账 200', r.status_code == 200)
    r.close()

    # ── 15. 诊断页面 ──
    section('15. 诊断页面')
    r = get('/diagnostics')
    check('诊断页面 200', r.status_code == 200)
    html = r.get_data(as_text=True); r.close()
    check('诊断含 Python 版本', 'python' in html.lower())

    r = get('/api/diagnostics')
    check('API 诊断 200', r.status_code == 200)
    r.close()

    # ── 16. 备份管理 ──
    section('16. 备份管理')
    r = get('/backups')
    check('备份列表 200', r.status_code == 200)
    r.close()

    with client.session_transaction() as sess:
        set_csrf(sess)
    r = post('/backups/create')
    check('创建备份重定向', r.status_code in (200, 302), str(r.status_code))
    r.close()

    backups = ledger_store.list_backups()
    check('备份已创建', len(backups) >= 1, f'共 {len(backups)} 个')

    if backups:
        bk = backups[0]
        fname = bk['filename']
        r = get(f'/backups/{fname}/download')
        check('下载备份 200', r.status_code == 200)
        r.close()

    # ── 17. 自启动状态 ──
    section('17. 自启动状态')
    status = helpers.autostart_status()
    check('自启动状态可获取', isinstance(status, dict))
    check('含 supported 字段', 'supported' in status)
    check('含 enabled 字段', 'enabled' in status)

    # ── 18. 模板版本 ──
    section('18. 模板版本')
    r = get(f'/template/{tpl_filename}/versions')
    check('模板版本 200', r.status_code == 200)
    r.close()

    # ── 19. 付款到期提醒 API ──
    section('19. 付款到期提醒 API')
    r = get('/api/payments/due-soon?days=30')
    check('到期提醒 200', r.status_code == 200)
    data = r.get_json(); r.close()
    check('含 count 字段', 'count' in data, str(data))
    check('含 total_amount 字段', 'total_amount' in data)

    # ── 20. 批量操作 ──
    section('20. 批量操作')
    result2 = ledger_store.list_contracts(per_page=100)
    all_ids = [c['id'] for c in result2.get('rows', [])]
    if len(all_ids) >= 2:
        # 20a. 批量更新状态
        with client.session_transaction() as sess:
            set_csrf(sess)
        batch_ids = all_ids[:2]
        r = post('/contracts/batch-status', data={
            'ids': json.dumps(batch_ids),
            'status': 'signed',
        })
        check('批量状态更新重定向', r.status_code == 302)
        r.close()

        # 验证
        for bid in batch_ids:
            c = ledger_store.get_contract(bid)
            check(f'合同 {bid} 状态为 signed', c and c.get('status') == 'signed', str(c.get('status')))

        # 20b. 超量拒绝
        with client.session_transaction() as sess:
            set_csrf(sess)
        too_many = list(range(200))
        r = post('/contracts/batch-delete', data={'ids': json.dumps(too_many)})
        check('超量删除被拒绝', r.status_code == 400)
        r.close()

    # ── 21. 合同台账分页 ──
    section('21. 台账分页')
    r = get('/contracts?page=1')
    check('分页 200', r.status_code == 200)
    r.close()

    # ── 22. 空数据安全性 ──
    section('22. 空数据/404 安全性')
    r = get('/contracts/99999')
    check('不存在的合同 404', r.status_code == 404)
    r.close()

    r = get('/contracts/99999/download')
    check('不存在合同下载 404', r.status_code == 404)
    r.close()

    with client.session_transaction() as sess:
        set_csrf(sess)
    r = post('/contracts/99999/payments/save', data={'plan_count': '0'})
    check('不存在合同付款计划 404', r.status_code == 404, f'status={r.status_code}')
    r.close()

    # ── 23. 模板操作 ──
    section('23. 模板删除')
    with client.session_transaction() as sess:
        set_csrf(sess)
    r = post(f'/template/{tpl_filename}/delete')
    check('模板删除重定向', r.status_code == 302)
    r.close()

    # 验证删除
    templates_after = [
        item
        for item in os.listdir(template_def.TEMPLATES_DIR)
        if item.endswith('.contract-template')
    ]
    check('模板已删除', tpl_filename not in templates_after, str(templates_after))

    return summary()


def run():
    import app as app_module

    global PASS, FAIL, _results
    PASS = 0
    FAIL = 0
    _results = []
    original_base_dir = app_module.BASE_DIR
    original_resource_dir = app_module.RESOURCE_DIR
    with tempfile.TemporaryDirectory() as runtime_dir:
        app_module.reset_runtime()
        test_app = app_module.create_app(
            runtime_base_dir=runtime_dir,
            resource_dir=original_resource_dir,
            run_maintenance=False,
            testing=True,
        )
        try:
            return _run_with_app(test_app)
        finally:
            app_module.reset_runtime()
            app_module.configure_runtime_paths(
                original_base_dir,
                original_resource_dir,
            )


if __name__ == '__main__':
    exit_code = run()
    sys.exit(exit_code)
