# -*- coding: utf-8 -*-
"""Create three end-to-end demo contracts for the order contract template."""

import json
import os
from decimal import Decimal, ROUND_HALF_UP

import app as app_module
# 确保运行时目录初始化
app_module.init_runtime(run_maintenance=False)

import ledger_store
import template_def
from utils.generation_utils import next_month_range


TEMPLATE_CANDIDATES = [
    '订货合同模板.contract-template',
    '订货.contract-template',
]


def find_template():
    """按关键词优先级查找模板，所有模板均不存在时才报错"""
    # 先尝试硬编码的候选
    for filename in TEMPLATE_CANDIDATES:
        path = os.path.join(template_def.TEMPLATES_DIR, filename)
        if os.path.exists(path):
            return filename, template_def.TemplateDef.load(path)

    # 回退：扫描所有模板，优先选择字段数最多的（最完整的模板）
    all_templates = template_def.list_templates()
    if not all_templates:
        raise FileNotFoundError('未找到任何合同模板，请先创建模板并上传样式文档')

    # 按 field_count 降序排列，优先选择最完整的模板
    all_templates.sort(key=lambda t: t['field_count'], reverse=True)
    best = all_templates[0]
    return best['filename'], template_def.TemplateDef.load(best['path'])


CASES = [
    {
        'no': 'DEMO-DH-2026-001',
        'name': '惯性导航组件订货合同',
        'supplier': '北京星航智造科技有限公司',
        'credit': '91110108MA00XH001A',
        'address': '北京市海淀区知春路88号航天科技园A座',
        'zip': '100086',
        'phone': '010-68180001',
        'bank': '中国银行北京中关村支行',
        'account_name': '北京星航智造科技有限公司',
        'account_no': '3482567890012345678',
        'legal': '周明',
        'contact': '李晨',
        'contact_phone': '13801010001',
        'owner': '王工',
        'owner_phone': '18600000001',
        'sign_date': '2026-05-18',
        'delivery_date': '2026-07-20',
        'target': '惯性导航组件',
        'products': [
            {'序号': '1', 'product_name': '惯性测量单元', 'spec': 'IMU-X7', 'uom': '套', 'qty': '8', 'unit_price': '9.50', 'tax_rate': '13%', 'remark': '含校准报告'},
            {'序号': '2', 'product_name': '导航控制板', 'spec': 'NCB-42', 'uom': '块', 'qty': '12', 'unit_price': '4.30', 'tax_rate': '13%', 'remark': '三防处理'},
        ],
        'pay_plans': [
            ('预付款', '合同签订后7日内', '2026-06-05', 30, 'unpaid', 0),
            ('验收款', '到货并验收合格后10日内', '2026-07-30', 60, 'unpaid', 0),
            ('质保金', '质保期满且无质量问题后', '2027-07-30', 10, 'unpaid', 0),
        ],
    },
    {
        'no': 'DEMO-DH-2026-002',
        'name': '遥测电缆组件订货合同',
        'supplier': '西安天枢电子设备有限公司',
        'credit': '91610131MA6U0002XB',
        'address': '陕西省西安市高新区锦业一路56号',
        'zip': '710065',
        'phone': '029-88220002',
        'bank': '招商银行西安高新支行',
        'account_name': '西安天枢电子设备有限公司',
        'account_no': '12990088220002288',
        'legal': '赵航',
        'contact': '陈晓',
        'contact_phone': '13902990002',
        'owner': '刘工',
        'owner_phone': '18600000002',
        'sign_date': '2026-05-20',
        'delivery_date': '2026-06-25',
        'target': '遥测电缆组件',
        'products': [
            {'序号': '1', 'product_name': '遥测电缆组件A型', 'spec': 'TC-A-18', 'uom': '套', 'qty': '20', 'unit_price': '2.35', 'tax_rate': '13%', 'remark': '带接插件'},
            {'序号': '2', 'product_name': '转接测试线束', 'spec': 'TC-T-06', 'uom': '套', 'qty': '10', 'unit_price': '1.15', 'tax_rate': '13%', 'remark': '随货交付'},
        ],
        'pay_plans': [
            ('一次总付款', '产品交付并收到合规发票后15日内', '2026-06-28', 100, 'partial', 200000),
        ],
    },
    {
        'no': 'DEMO-DH-2026-003',
        'name': '地面测试设备订货合同',
        'supplier': '上海启明航电系统有限公司',
        'credit': '91310115MA1K0003XC',
        'address': '上海市浦东新区张江高科技园区龙东大道3000号',
        'zip': '201203',
        'phone': '021-58880003',
        'bank': '交通银行上海张江支行',
        'account_name': '上海启明航电系统有限公司',
        'account_no': '31006688990000333',
        'legal': '孙远',
        'contact': '黄琳',
        'contact_phone': '13701880003',
        'owner': '张工',
        'owner_phone': '18600000003',
        'sign_date': '2026-05-22',
        'delivery_date': '2026-08-10',
        'target': '地面测试设备',
        'products': [
            {'序号': '1', 'product_name': '地面综合测试台', 'spec': 'GTS-300', 'uom': '台', 'qty': '1', 'unit_price': '168.00', 'tax_rate': '13%', 'remark': '含软件授权'},
            {'序号': '2', 'product_name': '专用测试适配器', 'spec': 'GTS-ADP-12', 'uom': '套', 'qty': '4', 'unit_price': '18.50', 'tax_rate': '13%', 'remark': '含备件'},
        ],
        'pay_plans': [
            ('预付款', '合同签订后10日内', '2026-06-15', 40, 'unpaid', 0),
            ('交付款', '设备到货并完成初验后15日内', '2026-08-25', 50, 'unpaid', 0),
            ('质保金', '质保期满后30日内', '2027-08-25', 10, 'unpaid', 0),
        ],
    },
]


# ═══════════════════════════════════════════════════════
#  数值 / 中文大写金额工具函数
# ═══════════════════════════════════════════════════════

from utils.cn_money import to_chinese


def product_total(products: list[dict]) -> float:
    """计算产品总价（万元）"""
    total = Decimal('0')
    for p in products:
        qty = Decimal(str(p.get('qty', '0')))
        price = Decimal(str(p.get('unit_price', '0')))
        total += qty * price
    return float(total)


def wan_to_yuan(wan: float) -> Decimal:
    """万元 → 元"""
    return Decimal(str(wan)) * Decimal('10000')


def money(value: Decimal) -> Decimal:
    """四舍五入到分"""
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


cn_money = to_chinese  # 向后兼容别名


def build_form(tpl, case):
    total_wan = product_total(case['products'])
    total_yuan = wan_to_yuan(total_wan)
    no_tax = money(total_yuan / Decimal('1.13'))
    tax = money(total_yuan - no_tax)
    first_pay = money(total_yuan * Decimal(str(case['pay_plans'][0][3])) / Decimal('100'))
    values = {
        '密级': '商密',
        '合同编号': case['no'],
        '合同名称': case['name'],
        '乙方单位名称': case['supplier'],
        '乙方单位名称_1': case['supplier'],
        '签订日期': case['sign_date'],
        '乙方统一社会信用代码': case['credit'],
        '乙方地址': case['address'],
        '乙方邮政编码': case['zip'],
        '乙方电话': case['phone'],
        '乙方开户银行': case['bank'],
        '乙方账户名': case['account_name'],
        '乙方账号': case['account_no'],
        '甲方联系人': case['owner'],
        '甲方联系方式': case['owner_phone'],
        '乙方法定代表人': case['legal'],
        '乙方联系人': case['contact'],
        '乙方联系方式': case['contact_phone'],
        '根据合同标的名称的生产和配套要求_北京中科宇航技术有限公司_以下简称甲方_与乙方单位名称_以下简称乙方_本着平等互利_高效务实的原则_经过充分协商_就合同标的名称订货一事达成一致意见并签订本合同': f"根据{case['target']}的生产和配套要求，北京中科宇航技术有限公司与{case['supplier']}就{case['target']}订货一事达成一致意见并签订本合同。",
        '配合完成的相关试验': '出厂检验、到货复验、接口联调试验',
        '提供的服务项目': '技术资料交付、现场技术支持、质量问题响应',
        '交付日期': case['delivery_date'],
        '交付产品名称': case['target'],
        '总计金额': f'{total_wan}万元',
        '执行的法律法规': '《中华人民共和国民法典》及国家相关质量、保密、税务管理规定',
        '合同标的': case['target'],
        '小写合同金额': f'{total_yuan}元',
        '大写合同金额': cn_money(total_yuan),
        '不含税金额': f'{no_tax}元',
        '税额': f'{tax}元',
        '字段名': '验收合格证明',
        '合同金额': f'{total_yuan}元',
        '付款时间': '分期支付',
        '付款第几笔': '1',
        '本笔支付款项百分比': f"{case['pay_plans'][0][3]}%",
        '本笔支付款项金额': f'{first_pay}元',
        '本笔支付款项大写金额': cn_money(first_pay),
        '本笔支付款项时间': case['pay_plans'][0][2],
        'N日内提供发票': '7',
        '税率': '13%',
        '乙方账户名称': case['account_name'],
        '乙方开户银行_1': case['bank'],
        '乙方银行账号': case['account_no'],
        '字段名_1': '验收资料',
        '逾期周期': '7',
        '字段名_2': '质量问题整改报告',
        '字段名_3': '保密审查资料',
    }
    table_rows = [
        [
            {'序号': '1', '文件名称': '技术协议', '文件号': f"JS-{case['no'][-3:]}", 'uom': '甲方', 'remark': '合同附件'},
            {'序号': '2', '文件名称': '质量保证要求', '文件号': f"QA-{case['no'][-3:]}", 'uom': '甲方', 'remark': '执行依据'},
        ],
        [
            {'序号': '1', '文件名称': '合格证', '文件号': f"COC-{case['no'][-3:]}", 'remark': '随货提交'},
            {'序号': '2', '文件名称': '检验报告', '文件号': f"IR-{case['no'][-3:]}", 'remark': '验收资料'},
        ],
        case['products'],
    ]
    table_index = 0
    form = {}
    for i, field in enumerate(tpl.data['fields']):
        fid = field.get('id', i)
        if field.get('field_type') == 'table':
            rows = table_rows[table_index] if table_index < len(table_rows) else []
            table_index += 1
            form[f'field_{fid}'] = json.dumps(rows, ensure_ascii=False)
            form[f'table_cols_{fid}'] = json.dumps(field.get('columns', []), ensure_ascii=False)
        else:
            form[f'field_{fid}'] = str(values.get(field.get('key'), values.get(field.get('label'), '演示数据')))
    return form, total_yuan


def add_confirmed_plans(contract_id, case, total_yuan):
    for plan in ledger_store.list_payment_plans(contract_id=contract_id):
        if plan.get('confirm_status') == 'pending':
            ledger_store.update_payment_plan(plan['id'], {
                'confirm_status': 'void',
                'remark': '演示：自动抓取的原文依据，已人工整理为正式付款计划。',
            })
    for phase, condition, due_date, ratio, status, paid in case['pay_plans']:
        due = money(Decimal(str(total_yuan)) * Decimal(str(ratio)) / Decimal('100'))
        ledger_store.insert_payment_plan(contract_id, {
            'phase_name': phase,
            'payment_type': 'fixed_date' if due_date else 'conditional',
            'trigger_event': condition,
            'due_date': due_date,
            'ratio': ratio,
            'due_amount': float(due),
            'paid_amount': float(paid),
            'paid_date': '2026-06-18' if paid else '',
            'condition_text': condition,
            'source_text': f'人工确认演示：{phase}，{condition}，支付合同金额的{ratio}%。',
            'confidence': 'high',
            'confirm_status': 'confirmed',
            'payment_status': status,
            'remark': '演示付款计划',
        })


def main():
    template_file, tpl = find_template()
    client = app_module.app.test_client()
    created = []
    for case in CASES:
        client.get('/template/' + template_file)
        form, total_yuan = build_form(tpl, case)
        resp = client.post('/generate', data=form)
        if resp.status_code != 200:
            raise RuntimeError(f"{case['no']} 生成失败: {resp.status_code} {resp.get_data(as_text=True)[:300]}")
        contract_id = int(resp.headers['X-Contract-Id'])
        ledger_store.update_contract(contract_id, {'status': 'active', 'owner': case['owner']})
        add_confirmed_plans(contract_id, case, total_yuan)
        created.append({
            'id': contract_id,
            'contract_no': case['no'],
            'title': case['name'],
            'amount': float(total_yuan),
            'detail_url': resp.headers.get('X-Contract-Detail-Url'),
        })

    start, end = next_month_range()
    next_demo_rows = [
        row for row in ledger_store.next_month_payment_plans(start, end)
        if str(row.get('contract_no', '')).startswith('DEMO-DH-2026-')
    ]
    result = {
        'template': tpl.name,
        'template_file': template_file,
        'source_docx': tpl.data.get('source_docx'),
        'field_count': len(tpl.data.get('fields', [])),
        'created': created,
        'next_month_range': [start, end],
        'next_month_demo_payments': [
            {
                'contract_no': row.get('contract_no'),
                'phase_name': row.get('phase_name'),
                'due_date': row.get('due_date'),
                'due_amount': row.get('due_amount'),
                'payment_status': row.get('payment_status'),
            }
            for row in next_demo_rows
        ],
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
