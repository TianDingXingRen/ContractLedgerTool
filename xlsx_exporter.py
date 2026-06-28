"""XLSX 导出模块 — 基于 openpyxl 生成付款计划和合同台账 Excel 文件"""

import math
import os

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# ── 样式常量 ──
_HEADER_FONT = Font(name='Microsoft YaHei', bold=True, size=11)
_TITLE_FONT = Font(name='Microsoft YaHei', bold=True, size=16)
_NORMAL_FONT = Font(name='Microsoft YaHei', size=11)
_HEADER_FILL = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')
_THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin'),
)


def _apply_header_style(ws, row, col_count):
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = _THIN_BORDER


def _num(value):
    try:
        v = float(value or 0)
        return v if math.isfinite(v) else 0
    except (TypeError, ValueError):
        return 0


def export_payment_plans(path, rows, title='下月付款计划'):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    headers = ['序号', '所属项目', '覆盖范围', '合同编号', '合同名称', '对方单位', '款项名称',
               '应付日期', '应付金额', '已付金额', '未付金额',
               '付款条件', '负责人', '备注']
    col_widths = [6, 22, 16, 18, 26, 24, 16, 14, 14, 14, 14, 36, 14, 24]

    # 标题行
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='center')

    # 表头（第3行）
    for ci, header in enumerate(headers, 1):
        ws.cell(row=3, column=ci, value=header)
    _apply_header_style(ws, 3, len(headers))

    # 数据行（从第4行开始）
    total_due = total_paid = 0
    for idx, row in enumerate(rows, 1):
        ri = idx + 3  # Excel 行号
        due = _num(row.get('due_amount'))
        paid = _num(row.get('paid_amount'))
        total_due += due
        total_paid += paid
        values = [
            idx,
            row.get('project_name') or '',
            (f"{row.get('coverage_start')}–{row.get('coverage_end')}号"
             if row.get('coverage_start') is not None and row.get('coverage_end') is not None else ''),
            row.get('contract_no') or '',
            row.get('contract_title') or '',
            row.get('counterparty') or '',
            row.get('phase_name') or '',
            row.get('due_date') or '',
            due, paid, round(due - paid, 2),
            row.get('condition_text') or '',
            row.get('owner') or '',
            row.get('remark') or '',
        ]
        for ci, val in enumerate(values, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.font = _NORMAL_FONT
            cell.border = _THIN_BORDER
            if ci in (9, 10, 11):
                cell.number_format = '#,##0.00'

    # 合计行
    summary_row = len(rows) + 4
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=8)
    if rows:
        ws.cell(row=summary_row, column=1, value='合计').font = _HEADER_FONT
        ws.cell(row=summary_row, column=9, value=round(total_due, 2)).number_format = '#,##0.00'
        ws.cell(row=summary_row, column=10, value=round(total_paid, 2)).number_format = '#,##0.00'
        ws.cell(row=summary_row, column=11, value=round(total_due - total_paid, 2)).number_format = '#,##0.00'
    else:
        ws.cell(row=summary_row, column=1, value='（无数据）').font = _HEADER_FONT
    for ci in range(1, len(headers) + 1):
        cell = ws.cell(row=summary_row, column=ci)
        cell.border = _THIN_BORDER

    # 列宽
    for ci, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = width

    wb.save(path)
    return path


def export_contracts(path, contracts, title='合同台账'):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    status_labels = {
        'draft': '草稿', 'signed': '已签订', 'active': '履行中',
        'completed': '已完成', 'void': '已作废',
    }
    headers = ['序号', '所属项目', '覆盖范围', '合同编号', '合同名称', '对方单位', '金额',
               '签订日期', '负责人', '状态', '创建时间', '付款计划数']
    col_widths = [6, 22, 16, 18, 26, 24, 14, 14, 14, 12, 14, 14]

    # 标题行
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='center')

    # 表头（第3行）
    for ci, header in enumerate(headers, 1):
        ws.cell(row=3, column=ci, value=header)
    _apply_header_style(ws, 3, len(headers))

    # 数据行
    total_amount = 0
    for idx, c in enumerate(contracts, 1):
        ri = idx + 3
        amount = _num(c.get('amount'))
        total_amount += amount
        values = [
            idx,
            c.get('project_name') or '',
            (f"{c.get('coverage_start')}–{c.get('coverage_end')}号"
             if c.get('coverage_start') is not None and c.get('coverage_end') is not None else ''),
            c.get('contract_no') or '',
            c.get('title') or '',
            c.get('counterparty') or '',
            amount,
            c.get('sign_date') or '',
            c.get('owner') or '',
            status_labels.get(c.get('status'), c.get('status', '')),
            (c.get('created_at') or '')[:10],
            c.get('plan_count', 0),
        ]
        for ci, val in enumerate(values, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.font = _NORMAL_FONT
            cell.border = _THIN_BORDER
            if ci == 7:
                cell.number_format = '#,##0.00'

    # 合计行
    summary_row = len(contracts) + 4
    ws.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=6)
    if contracts:
        ws.cell(row=summary_row, column=1, value='合计').font = _HEADER_FONT
        ws.cell(row=summary_row, column=7, value=round(total_amount, 2)).number_format = '#,##0.00'
    else:
        ws.cell(row=summary_row, column=1, value='（无数据）').font = _HEADER_FONT
    for ci in range(1, len(headers) + 1):
        ws.cell(row=summary_row, column=ci).border = _THIN_BORDER

    # 列宽
    for ci, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = width

    wb.save(path)
    return path
