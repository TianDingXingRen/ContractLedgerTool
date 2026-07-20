from docx import Document
from openpyxl import load_workbook
import pytest

import docx_builder
import pdf_exporter
import xlsx_exporter


def test_generated_docx_matches_semantic_snapshot(tmp_path):
    output = tmp_path / 'contract.docx'
    template = {
        'template_name': '采购合同',
        'fields': [
            {'key': 'party', 'label': '供应商', 'field_type': 'text'},
            {
                'key': 'items', 'label': '采购明细', 'field_type': 'table',
                'columns': [
                    {'key': 'name', 'label': '物资名称'},
                    {'key': 'quantity', 'label': '数量'},
                ],
            },
        ],
    }
    docx_builder.generate_from_scratch(
        template,
        {'party': '北辰精工有限公司', 'items': [{'name': '精密轴承', 'quantity': '47'}]},
        output,
    )

    document = Document(output)
    snapshot = {
        'paragraphs': [paragraph.text for paragraph in document.paragraphs if paragraph.text],
        'tables': [
            [[cell.text for cell in row.cells] for row in table.rows]
            for table in document.tables
        ],
    }

    assert snapshot == {
        'paragraphs': ['采购合同', '供应商：北辰精工有限公司'],
        'tables': [[['物资名称', '数量'], ['精密轴承', '47']]],
    }


def test_generated_xlsx_matches_semantic_snapshot(tmp_path):
    output = tmp_path / 'payments.xlsx'
    xlsx_exporter.export_payment_plans(output, [{
        'project_name': '西岭升级项目', 'coverage_start': 8, 'coverage_end': 16,
        'contract_no': 'HT-2026-071', 'contract_title': '设备采购合同',
        'counterparty': '北辰精工有限公司', 'phase_name': '到货款',
        'due_date': '2026-08-19', 'due_amount': 47200.35, 'paid_amount': 12000.10,
        'condition_text': '到货验收后付款', 'owner': 'Shao', 'remark': '',
    }])

    workbook = load_workbook(output, data_only=False, read_only=True)
    try:
        sheet = workbook.active
        assert [sheet.cell(3, column).value for column in range(1, 15)] == [
            '序号', '所属项目', '覆盖范围', '合同编号', '合同名称', '对方单位',
            '款项名称', '应付日期', '应付金额', '已付金额', '未付金额',
            '付款条件', '负责人', '备注',
        ]
        assert [sheet.cell(4, column).value for column in range(1, 15)] == [
            1, '西岭升级项目', '8–16号', 'HT-2026-071', '设备采购合同',
            '北辰精工有限公司', '到货款', '2026-08-19', 47200.35, 12000.1,
            35200.25, '到货验收后付款', 'Shao', None,
        ]
    finally:
        workbook.close()


def test_pdf_output_validator_rejects_external_tool_garbage(tmp_path):
    invalid = tmp_path / 'invalid.pdf'
    invalid.write_bytes(b'not-a-pdf')
    with pytest.raises(RuntimeError, match='输出无效'):
        pdf_exporter._validate_pdf_output(invalid)

    valid = tmp_path / 'valid.pdf'
    valid.write_bytes(b'%PDF-1.7\n%%EOF')
    assert pdf_exporter._validate_pdf_output(valid) == valid
