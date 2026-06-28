# -*- coding: utf-8 -*-
"""
Generate 10 test contracts from template1 and template2, then verify all features.
"""
import json, os, sys, shutil, uuid, time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template_def
from utils.cn_money import to_chinese as num_to_chinese
from utils.helpers import detect_markers, create_ledger_record, recalculate_scalar_fields
from utils.helpers import OUTPUT_FOLDER as _CFG_OUTPUT, UPLOAD_FOLDER as _CFG_UPLOAD

# 确保路径已初始化（此脚本作为独立工具运行时需要）
if _CFG_OUTPUT is None or _CFG_UPLOAD is None:
    import app as _app
    _app.init_runtime(run_maintenance=False)
    from utils.helpers import OUTPUT_FOLDER as OUTPUT_FOLDER, UPLOAD_FOLDER as UPLOAD_FOLDER
else:
    OUTPUT_FOLDER = _CFG_OUTPUT
    UPLOAD_FOLDER = _CFG_UPLOAD

COMPANIES = [
    {"name": "北京航天科技有限公司", "credit_code": "91110108MA01ABCD1X",
     "address": "北京市海淀区中关村南大街5号", "postal": "100081", "phone": "010-62551234",
     "bank": "中国工商银行北京海淀支行", "account": "0200012345678901234",
     "legal_rep": "张伟", "contact": "李强", "contact_phone": "13801001234"},
    {"name": "上海精密仪器制造有限公司", "credit_code": "91310115MA01BCDE2Y",
     "address": "上海市浦东新区张江高科技园区碧波路888号", "postal": "201203", "phone": "021-50891234",
     "bank": "中国建设银行上海浦东分行", "account": "3100123456789012345",
     "legal_rep": "王芳", "contact": "赵明", "contact_phone": "13902105678"},
    {"name": "成都电子信息工程有限公司", "credit_code": "91510100MA01CDEF3Z",
     "address": "成都市高新区天府大道南段1688号", "postal": "610041", "phone": "028-85331234",
     "bank": "中国农业银行成都高新支行", "account": "2200123456789012345",
     "legal_rep": "陈刚", "contact": "刘洋", "contact_phone": "18602807890"},
    {"name": "深圳华强电子技术有限公司", "credit_code": "91440300MA01DFGH4A",
     "address": "深圳市南山区科技园科苑路15号", "postal": "518057", "phone": "0755-86101234",
     "bank": "招商银行深圳南山支行", "account": "7559123456789012",
     "legal_rep": "黄丽", "contact": "周杰", "contact_phone": "13510803456"},
    {"name": "武汉光谷光电科技有限公司", "credit_code": "91420100MA01EGHI5B",
     "address": "武汉市东湖新技术开发区光谷大道88号", "postal": "430074", "phone": "027-87181234",
     "bank": "中国银行武汉光谷支行", "account": "5719123456789012345",
     "legal_rep": "孙涛", "contact": "吴昊", "contact_phone": "15902701234"},
]

PRODUCTS = [
    {"name": "高精度陀螺仪组件", "model": "GY-2026A", "unit": "套", "qty": "5", "price": "85000", "total": 425000, "tax_rate": "13%"},
    {"name": "惯性导航模块", "model": "INS-2000B", "unit": "台", "qty": "3", "price": "120000", "total": 360000, "tax_rate": "13%"},
    {"name": "加速度计传感器", "model": "ACL-500X", "unit": "个", "qty": "20", "price": "4500", "total": 90000, "tax_rate": "13%"},
    {"name": "光纤陀螺仪", "model": "FOG-800T", "unit": "套", "qty": "2", "price": "200000", "total": 400000, "tax_rate": "13%"},
    {"name": "微机电系统模块", "model": "MEMS-300", "unit": "个", "qty": "50", "price": "2800", "total": 140000, "tax_rate": "13%"},
    {"name": "导航计算机板卡", "model": "NCB-1500", "unit": "块", "qty": "8", "price": "36000", "total": 288000, "tax_rate": "13%"},
    {"name": "姿态传感器组件", "model": "ASC-600P", "unit": "台", "qty": "4", "price": "65000", "total": 260000, "tax_rate": "13%"},
    {"name": "温度补偿晶体振荡器", "model": "TCXO-25M", "unit": "个", "qty": "100", "price": "1200", "total": 120000, "tax_rate": "13%"},
    {"name": "嵌入式数据处理单元", "model": "EDPU-400", "unit": "套", "qty": "6", "price": "55000", "total": 330000, "tax_rate": "13%"},
    {"name": "精密测量传感器阵列", "model": "PMSA-12", "unit": "阵列", "qty": "3", "price": "150000", "total": 450000, "tax_rate": "13%"},
]

CONFIDENTIALITY = ["公开", "内部", "秘密", "机密"]


def make_values(fields, company, product, idx, tpl_idx):
    today = date.today()
    delivery_date = today + timedelta(days=30 + idx * 15)
    sign_date = today.strftime('%Y年%m月')
    delivery_str = delivery_date.strftime('%Y年%m月%d日')
    contract_no = f"HT-2026-{tpl_idx*5+idx+1:03d}"
    contract_title = f"{product['name']}采购合同"
    total_amount = float(product['total'])
    tax_rate_val = 0.13
    tax_amount = round(total_amount * tax_rate_val / (1 + tax_rate_val), 2)
    untaxed = round(total_amount - tax_amount, 2)
    warranty = (idx % 3) + 1
    conf_level = CONFIDENTIALITY[idx % len(CONFIDENTIALITY)]
    pmt_date1 = (today + timedelta(days=15 + idx * 10)).strftime('%Y-%m-%d')
    pmt_date2 = (today + timedelta(days=45 + idx * 10)).strftime('%Y-%m-%d')
    pmt_date3 = (today + timedelta(days=75 + idx * 10)).strftime('%Y-%m-%d')

    values = {}
    for f in fields:
        key = f.get('key', '')
        lbl = f.get('label', '')
        ftype = f.get('field_type', 'text')

        if ftype == 'table':
            if '任务依据' in lbl:
                values[key] = [
                    {"任务依据文件名称": f"技术协议-{contract_no}", "任务依据文件号": f"TA-{2026000+tpl_idx*5+idx+1}", "编制单位": "中国航空工业集团", "备注": "第1版"},
                    {"任务依据文件名称": f"质量保证协议-{contract_no}", "任务依据文件号": f"QA-{2026000+tpl_idx*5+idx+1}", "编制单位": "中国航空工业集团", "备注": ""},
                ]
            elif '生产依据' in lbl:
                values[key] = [
                    {"生产依据文件名称": f"产品规格书-{product['model']}", "生产依据文件号": f"SPC-{2026000+tpl_idx*5+idx+1}", "备注": ""},
                    {"生产依据文件名称": "工艺规范-通用", "生产依据文件号": "PRC-GEN-2026", "备注": "最新版"},
                ]
            elif '标的' in lbl or '产品' in lbl:
                values[key] = [{
                    "产品名称": product['name'], "规格型号": product['model'],
                    "单位": product['unit'], "订购数量": product['qty'],
                    "单价/元": product['price'], "合计/元": str(product['total']),
                    "增值税率": product['tax_rate'], "备注": "按技术协议执行"
                }]
            elif '配套' in lbl:
                values[key] = [
                    {"配套资料名称": "产品合格证", "数量": "1", "备注": f"每{product['unit']}1份"},
                    {"配套资料名称": "出厂检验报告", "数量": "1", "备注": f"每{product['unit']}1份"},
                    {"配套资料名称": "使用维护说明书", "数量": "2", "备注": "纸质+电子版"},
                ]
            elif '试验' in lbl or '配合' in lbl:
                values[key] = [
                    {"配合完成试验": "环境应力筛选试验", "备注": "按照GJB 150A执行"},
                    {"配合完成试验": "振动试验", "备注": "按照GJB 150.16A执行"},
                ]
            elif '服务' in lbl:
                values[key] = [
                    {"提供的服务": "现场安装调试", "备注": f"预计{2+idx%3}人天"},
                    {"提供的服务": "操作培训", "备注": f"培训{3+idx%5}名操作人员"},
                    {"提供的服务": "技术咨询", "备注": "7×24电话支持"},
                ]
            else:
                values[key] = [{}]
        else:
            if '密级' in key:
                values[key] = conf_level
            elif '合同编号' in key:
                values[key] = contract_no
            elif '合同名称' in key:
                values[key] = contract_title
            elif '乙方单位名称' in key:
                values[key] = company['name']
            elif '签订日期' in key or '签约日期' in key:
                values[key] = sign_date
            elif '统一社会信用代码' in key:
                values[key] = company['credit_code']
            elif key in ('乙方地址',):
                values[key] = company['address']
            elif '邮政编码' in key:
                values[key] = company['postal']
            elif key in ('乙方电话',):
                values[key] = company['phone']
            elif '开户银行' in key:
                values[key] = company['bank']
            elif '账号' in key:
                values[key] = company['account']
            elif '法定代表人' in key:
                values[key] = company['legal_rep']
            elif '联系人' in key:
                values[key] = company['contact']
            elif '联系方式' in key:
                values[key] = company['contact_phone']
            elif '交付日期' in key or '交货日期' in key:
                values[key] = delivery_str
            elif '质保' in key and ('年' in key or '期' in lbl):
                values[key] = str(warranty)
            elif '质保' in key:
                values[key] = f"免费保修{warranty}年"
            elif key == '字段名' and '字段名' in lbl:
                values[key] = '2'
            elif '付款第几笔' in key:
                values[key] = '1'
            elif '本笔支付款项百分比' in key:
                values[key] = '30'
            elif '本笔支付款项金额' in key:
                values[key] = f'{total_amount * 0.3:,.2f}'
            elif '本笔支付款项大写金额' in key:
                values[key] = num_to_chinese(total_amount * 0.3) + '元整'
            elif '本笔支付款项时间' in key or '付款时间' in key:
                values[key] = pmt_date1
            elif 'N日内提供发票' in key:
                values[key] = '30'
            elif '总价款' in key or '合同款' in key:
                values[key] = f"订购{product['name']}产品的合同总价款（含税）小写：人民币{total_amount:,.2f}元，大写：{num_to_chinese(total_amount)}元整，税率13%，不含税金额{untaxed:,.2f}元，税额{tax_amount:,.2f}元。"
            elif '大写' in key:
                values[key] = num_to_chinese(total_amount) + '元整'
            elif '总金额' in key or ('金额' in key and '合同' in key):
                values[key] = f'{total_amount:,.2f}'
            elif '不含税' in key:
                values[key] = f'{untaxed:,.2f}'
            elif '税额' in key:
                values[key] = f'{tax_amount:,.2f}'
            elif '结算方式' in key or '付款方式' in key:
                values[key] = (
                    f"结算方式及期限(采用以下第2种方式)：\n"
                    f"① 一次总付：人民币---元，时间：---；\n"
                    f"② 分期支付：\n"
                    f"第1笔：支付合同总额的30%，即人民币{total_amount*0.3:,.2f}元，"
                    f"大写：{num_to_chinese(total_amount*0.3)}元整，时间：{pmt_date1}；\n"
                    f"第2笔：支付合同总额的40%，即人民币{total_amount*0.4:,.2f}元，"
                    f"大写：{num_to_chinese(total_amount*0.4)}元整，时间：{pmt_date2}；\n"
                    f"第3笔：支付合同总额的30%，即人民币{total_amount*0.3:,.2f}元，"
                    f"大写：{num_to_chinese(total_amount*0.3)}元整，时间：{pmt_date3}。"
                )
            elif '发票' in key:
                values[key] = f"甲方完成单套产品交付验收后30日内，乙方应提供给甲方单套产品等额的增值税专用发票，本合同项下产品采购所涉及的13%增值税由乙方承担。"
            elif '税率' in key:
                values[key] = '13%'
            elif '合同摘要' in key or '摘要' in key:
                values[key] = f"本合同为{product['name']}采购合同，由中航凯航航空科技有限公司向{company['name']}采购{product['qty']}{product['unit']}{product['name']}（型号{product['model']}），合同总额{total_amount:,.2f}元（含税）。"
            elif '甲方地址' in key:
                values[key] = "北京市北京经济技术开发区地盛北街22号院西口2号楼8层801室"
            elif '甲方统一社会信用代码' in key:
                values[key] = '91110106MA003EBQ4D'
            elif '甲方邮政编码' in key:
                values[key] = '100023'
            elif '甲方电话' in key:
                values[key] = '010-88881234'
            elif '甲方开户银行' in key:
                values[key] = '中国工商银行北京经济技术开发区支行'
            elif '甲方账号' in key:
                values[key] = '0200123456789012345'
            elif '甲方' in key and '名称' in key:
                values[key] = "中航凯航航空科技有限公司"
            elif '合同签订地' in key:
                values[key] = '北京市'
            elif '争议' in key:
                values[key] = '如发生争议，双方应友好协商解决；协商不成的，提交北京仲裁委员会按该会仲裁规则仲裁。'
            elif '管辖' in key or '法律适用' in key:
                values[key] = '本合同适用中华人民共和国法律。'
            elif '合同份数' in key:
                values[key] = '本合同一式4份，甲乙双方各执2份，具有同等法律效力。'
            elif '生效' in key:
                values[key] = '本合同自双方签字盖章之日起生效。'
            elif '保密' in key:
                values[key] = f"双方应对本合同涉及的技术信息和商务信息予以保密，保密期限为合同履行完毕后{3+idx}年。"
            elif '验收' in key:
                values[key] = '产品交付甲方后，按照甲方采购验收标准进行验收，验收合格后办理入库手续。'
            elif '包装' in key:
                values[key] = '乙方应采用适合长途运输的防潮、防震、防静电包装，确保产品安全送达甲方指定地点。'
            elif '运输' in key:
                values[key] = '由乙方负责运输至甲方指定地点，运输费用由乙方承担。'
            elif '知识产权' in key:
                values[key] = '本合同履行过程中产生的技术成果归甲方所有。'
            elif '不可抗力' in key:
                values[key] = '因不可抗力导致合同无法履行的，受不可抗力影响一方应及时书面通知对方，并在15日内提供相关证明。'
            elif '期限' in key or '有效期' in key:
                values[key] = f'本合同自签订之日起生效，有效期至{date.today().year + 1}年{date.today().month}月{date.today().day}日。'
            elif '内容' in key and '合同' in key:
                values[key] = f"根据{product['name']}生产和配套要求，中航凯航航空科技有限公司（以下简称甲方）与{company['name']}（以下简称乙方）本着平等互利、高效务实的原则，经过充分协商，就{product['name']}订货一事达成一致意见并签订本合同。"
            elif '名称' in key:
                values[key] = product['name']
            elif '数量' in key:
                values[key] = product['qty']
            elif '单价' in key:
                values[key] = product['price']
            elif '日期' in key:
                values[key] = sign_date
            elif '金额' in key:
                values[key] = f'{total_amount:,.2f}'
            else:
                values[key] = f'[{lbl}]'

    return values


def main():
    print("=" * 60)
    print("Contract Generation Tool - Test Contract Batch Generator")
    print("=" * 60)

    desktop = os.path.expanduser(r"~\Desktop")
    template_files = {
        "Template1": os.path.join(desktop, "模板1.docx"),
        "Template2": os.path.join(desktop, "模板2.docx"),
    }

    all_contracts = []

    for tpl_idx, (tpl_label, src_path) in enumerate(template_files.items()):
        if not os.path.exists(src_path):
            print(f"\n[SKIP] {tpl_label}: file not found at {src_path}")
            continue

        print(f"\n[Template: {tpl_label}] Copying and scanning...")
        sid = uuid.uuid4().hex
        stored_name = f"{sid}.docx"
        dest = os.path.join(UPLOAD_FOLDER, stored_name)
        shutil.copy2(src_path, dest)

        fields = detect_markers(dest)
        print(f"  Detected {len(fields)} field markers")

        tpl_data = {
            'format_version': '1.0',
            'template_name': f'{tpl_label}_Test',
            'source_docx': stored_name,
            'fields': fields,
        }
        tpl = template_def.TemplateDef(tpl_data)
        tpl_path = tpl.save()
        print(f"  Template saved: {os.path.basename(tpl_path)}")

        from docx_builder import apply_text_field, apply_table_field
        from docx import Document

        for i in range(5):
            company = COMPANIES[i]
            product = PRODUCTS[tpl_idx * 5 + i]

            output_name = f"Contract_{tpl_label}_{i+1:02d}_{company['name']}.docx"
            output_path = os.path.join(OUTPUT_FOLDER, f"test_{uuid.uuid4().hex[:8]}_{output_name}")

            values = make_values(fields, company, product, i, tpl_idx)
            recalculate_scalar_fields(fields, values)

            try:
                doc = Document(src_path)
                import field_eval
                ordered_fields = field_eval.sort_fields_by_dependency(fields)

                for field in ordered_fields:
                    ftype = field['field_type']
                    key = field['key']
                    if ftype == 'table':
                        apply_table_field(doc, field, values.get(key, []))
                    else:
                        apply_text_field(doc, field.get('location', {}), values.get(key, ''),
                                        field.get('label', ''), key)

                doc.save(output_path)
                cid = create_ledger_record(tpl, fields, values, output_path)
                all_contracts.append({
                    'id': cid, 'tpl': tpl_label, 'company': company['name'],
                    'title': f"{product['name']}采购合同", 'amount': product['total'],
                })
                print(f"  OK [{i+1}/5] ID={cid} | {product['name']} | {company['name']} | CNY {product['total']:,.2f}")
            except Exception as e:
                print(f"  FAIL [{i+1}/5]: {e}")
                import traceback
                traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"TOTAL: {len(all_contracts)} contracts generated")
    for c in all_contracts:
        print(f"  ID={c['id']} | {c['tpl']} | {c['title']} | {c['company']} | CNY {c['amount']:,.2f}")
    print(f"{'=' * 60}")
    return all_contracts


if __name__ == '__main__':
    main()
