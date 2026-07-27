import io

import pytest
from openpyxl import load_workbook

import ledger_store
import xlsx_exporter


def _contract_with_serials(*, title='月报合同', project='火箭项目'):
    contract_id = ledger_store.create_contract({
        'contract_no': f'HT-{title}',
        'title': title,
        'counterparty': '乙方科技有限公司',
        'amount': 3_000_000,
        'status': 'active',
        'project_name': project,
        'coverage_start': 101,
        'coverage_end': 102,
    }, {'甲方': '甲方技术有限公司'}, f'/{title}.docx')
    serials = ledger_store.list_contract_serials(contract_id)
    ledger_store.save_contract_serial_amounts(contract_id, [
        {'id': serials[0]['id'], 'amount': '1200000', 'remark': ''},
        {'id': serials[1]['id'], 'amount': '1800000', 'remark': ''},
    ])
    return contract_id, ledger_store.list_contract_serials(contract_id)


def test_contract_serial_ledger_is_generated_and_validates_plan_links(tmp_db):
    contract_id, serials = _contract_with_serials()
    assert [row['serial_no'] for row in serials] == [101, 102]
    assert [row['serial_amount'] for row in serials] == [1_200_000, 1_800_000]

    plan_id = ledger_store.insert_payment_plan(contract_id, {
        'contract_serial_id': serials[0]['id'],
        'phase_name': '首付款',
        'due_date': '2026-05-20',
        'due_amount': 120_000,
        'confirm_status': 'confirmed',
    })
    plan = ledger_store.get_payment_plan(plan_id)
    assert plan['serial_no'] == 101
    assert plan['serial_amount'] == 1_200_000

    other_id, other_serials = _contract_with_serials(title='另一合同')
    assert other_id != contract_id
    with pytest.raises(ValueError, match='不属于当前合同'):
        ledger_store.insert_payment_plan(contract_id, {
            'contract_serial_id': other_serials[0]['id'],
            'phase_name': '错误关联',
        })

    ledger_store.update_contract(contract_id, {
        'coverage_start': 102,
        'coverage_end': 103,
    })
    all_serials = ledger_store.list_contract_serials(
        contract_id, include_inactive=True
    )
    assert [(row['serial_no'], row['status']) for row in all_serials] == [
        (101, 'inactive'), (102, 'active'), (103, 'active'),
    ]


def test_monthly_report_groups_nodes_by_contract_serial_without_notice_data(tmp_db):
    contract_id, serials = _contract_with_serials()
    serial_id = serials[0]['id']
    ledger_store.insert_payment_plans(contract_id, [
        {
            'contract_serial_id': serial_id,
            'phase_name': '首付款',
            'due_date': '2026-04-20',
            'due_amount': 300_000,
            'paid_amount': 100_000,
            'paid_date': '2026-04-21',
            'confirm_status': 'confirmed',
            'remark': '上月未付原因：审批尚未完成',
        },
        {
            'contract_serial_id': serial_id,
            'phase_name': '进度款',
            'due_date': '2026-05-20',
            'due_amount': 500_000,
            'confirm_status': 'confirmed',
            'condition_text': '完成阶段验收',
            'remark': '银承：6个月',
        },
        {
            'contract_serial_id': serial_id,
            'phase_name': '已付款节点',
            'due_date': '2026-03-20',
            'due_amount': 100_000,
            'paid_amount': 100_000,
            'paid_date': '2026-03-20',
            'confirm_status': 'confirmed',
        },
        {
            'contract_serial_id': serial_id,
            'phase_name': '尾款',
            'due_date': '2026-08-20',
            'due_amount': 300_000,
            'confirm_status': 'confirmed',
        },
        {
            'phase_name': '待补编号',
            'due_date': '2026-05-25',
            'due_amount': 10_000,
            'confirm_status': 'confirmed',
        },
    ])

    report = ledger_store.build_monthly_payment_report('2026-05')
    assert report['node_count'] == 4
    assert len(report['rows']) == 1
    row = report['rows'][0]
    assert row['serial_no'] == 101
    assert row['serial_amount_minor'] == 120_000_000
    assert row['current_month_minor'] == 50_000_000
    assert row['previous_unpaid_minor'] == 20_000_000
    assert row['planned_payment_minor'] == 70_000_000
    assert row['party_a'] == '甲方技术有限公司'
    assert row['bank_acceptance'] == '6个月'
    assert row['prior_unpaid_reason'] == '审批尚未完成'
    assert report['diagnostics']['unassigned_serial_count'] == 1


def test_monthly_report_export_matches_template_semantics(tmp_db, tmp_path):
    contract_id, serials = _contract_with_serials()
    ledger_store.insert_payment_plan(contract_id, {
        'contract_serial_id': serials[0]['id'],
        'phase_name': '本月进度款',
        'due_date': '2026-05-20',
        'due_amount': 500_000,
        'confirm_status': 'confirmed',
        'condition_text': '完成阶段验收',
    })
    report = ledger_store.build_monthly_payment_report('2026-05')
    output = tmp_path / 'monthly.xlsx'
    xlsx_exporter.export_monthly_payment_plan_report(output, report)

    workbook = load_workbook(output, data_only=False)
    try:
        assert workbook.sheetnames == ['汇总', '火箭项目']
        summary = workbook['汇总']
        detail = workbook['火箭项目']
        assert summary['A1'].value.startswith('2026年5月合同付款计划汇总')
        assert summary['B3'].value == '2026年5月计划付款合计'
        assert detail['A3'].value == '项目名称'
        assert detail['B3'].value == '合同内编号'
        assert detail['G3'].value == '本编号金额'
        assert detail['A4'].value == '火箭项目'
        assert detail['B4'].value == 101
        assert detail['G4'].value == 120
        assert detail['H4'].value == 50
        assert detail['H4'].fill.fgColor.rgb in {'00FFF2CC', 'FFF2CC'}
        assert detail['J4'].value == 50
        assert detail['L4'].value == '=J4+K4'
        assert summary['B4'].value.startswith("='火箭项目'!")
    finally:
        workbook.close()


def test_monthly_report_route_and_payment_page(client):
    contract_id, serials = _contract_with_serials()
    ledger_store.insert_payment_plan(contract_id, {
        'contract_serial_id': serials[0]['id'],
        'phase_name': '本月付款',
        'due_date': '2026-05-20',
        'due_amount': 100_000,
        'confirm_status': 'confirmed',
    })

    page = client.get('/payment-plans')
    assert page.status_code == 200
    assert '导出月度模板' in page.get_data(as_text=True)
    assert 'type="month"' in page.get_data(as_text=True)
    detail = client.get(f'/contracts/{contract_id}?tab=payments')
    detail_html = detail.get_data(as_text=True)
    assert '合同编号台账' in detail_html
    assert 'name="plan_0_contract_serial_id"' in detail_html
    assert '不依赖投产通知' in detail_html

    response = client.get('/payment-plans/export?report_month=2026-05')
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.data), data_only=False)
    try:
        assert workbook.sheetnames == ['汇总', '火箭项目']
    finally:
        workbook.close()
    assert client.get('/payment-plans/export?report_month=2026-13').status_code == 400


def test_empty_monthly_report_has_no_circular_total(tmp_db, tmp_path):
    report = ledger_store.build_monthly_payment_report('2026-05')
    output = tmp_path / 'empty-monthly.xlsx'
    xlsx_exporter.export_monthly_payment_plan_report(output, report)
    workbook = load_workbook(output, data_only=False)
    try:
        assert workbook.sheetnames == ['汇总']
        assert workbook['汇总']['B4'].value == 0
        assert '未发现影响本报表的缺失项' in workbook['汇总']['A6'].value
    finally:
        workbook.close()
