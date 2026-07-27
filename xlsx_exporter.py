"""XLSX 导出模块 — 基于 openpyxl 生成付款计划和合同台账 Excel 文件"""

import math
import os
import re

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from utils.security import safe_spreadsheet_value

# ── 样式常量 ──
_HEADER_FONT = Font(name='Microsoft YaHei', bold=True, size=11)
_TITLE_FONT = Font(name='Microsoft YaHei', bold=True, size=16)
_NORMAL_FONT = Font(name='Microsoft YaHei', size=11)
_HEADER_FILL = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')
_PAID_FILL = PatternFill(start_color='C6E0B4', end_color='C6E0B4', fill_type='solid')
_CURRENT_FILL = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
_WARNING_FILL = PatternFill(start_color='FCE4D6', end_color='FCE4D6', fill_type='solid')
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
    title_cell = ws.cell(
        row=1, column=1, value=safe_spreadsheet_value(title)
    )
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
            cell = ws.cell(row=ri, column=ci, value=safe_spreadsheet_value(val))
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

    try:
        wb.save(path)
    finally:
        wb.close()
    return path


def _minor_to_wan(value):
    if value is None:
        return None
    return round(int(value) / 1_000_000, 2)


def _safe_sheet_name(value, used):
    name = re.sub(r'[\[\]:*?/\\]', '_', str(value or '未归类项目')).strip() or '未归类项目'
    name = name[:31]
    candidate = name
    suffix = 2
    while candidate in used:
        tail = f'-{suffix}'
        candidate = f'{name[:31-len(tail)]}{tail}'
        suffix += 1
    used.add(candidate)
    return candidate


def _style_monthly_sheet(ws, last_col, data_end_row):
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A4'
    ws.auto_filter.ref = f'A3:{get_column_letter(last_col)}{max(3, data_end_row)}'
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 28
    ws.row_dimensions[3].height = 58
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = '1:3'


def export_monthly_payment_plan_report(path, report):
    """Export the reference-style monthly workbook in ten-thousand yuan.

    ``report`` is built by ``ledger_store.build_monthly_payment_report`` and
    intentionally contains no production-notice data.
    """
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = '汇总'
    used_sheet_names = {'汇总'}
    month_text = str(report['report_month'])
    year, month = month_text.split('-')
    display_month = f'{int(year)}年{int(month)}月'
    node_count = max(1, int(report.get('node_count') or 1))
    project_refs = []

    base_headers = [
        '项目名称', '合同内编号', '合同编号', '合同名称',
        '甲方', '乙方（全称）', '本编号金额',
    ]
    tail_headers = [
        '本月计划付款', '以前月份计划未付款', '计划付款合计',
        '合同约定本次付款需满足条件', '超过合同付款时间',
        '银行承兑', '上月已做计划未付款说明',
    ]
    for project in report.get('projects', []):
        sheet_name = _safe_sheet_name(project['project_name'], used_sheet_names)
        ws = wb.create_sheet(sheet_name)
        headers = list(base_headers)
        for node_index in range(1, node_count + 1):
            headers.extend([
                f'付款节点#{node_index}\n（金额）',
                f'付款节点#{node_index}\n（预期时间+支付条件）',
            ])
        headers.extend(tail_headers)
        last_col = len(headers)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
        ws.cell(
            1, 1,
            '填表注意事项：1、金额单位为万元；2、金额右对齐并保留2位；'
            '3、绿色表示已付款；4、黄色表示计划本月付款；'
            '5、编号和付款计划独立维护，不读取投产通知。',
        )
        ws.cell(1, 1).font = Font(name='Microsoft YaHei', size=10, color='666666')
        ws.cell(1, 1).alignment = Alignment(wrap_text=True, vertical='center')
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
        ws.cell(2, 1, f'{display_month}付款明细表    单位：万元')
        ws.cell(2, 1).font = _TITLE_FONT
        ws.cell(2, 1).alignment = Alignment(horizontal='center', vertical='center')
        for column, header in enumerate(headers, 1):
            ws.cell(3, column, safe_spreadsheet_value(header))
        _apply_header_style(ws, 3, last_col)
        ws.cell(3, 1).fill = PatternFill(
            start_color='4472C4', end_color='4472C4', fill_type='solid'
        )
        for cell in ws[3]:
            cell.fill = PatternFill(
                start_color='4472C4', end_color='4472C4', fill_type='solid'
            )
            cell.font = Font(name='Microsoft YaHei', bold=True, size=10, color='FFFFFF')
            cell.alignment = Alignment(
                horizontal='center', vertical='center', wrap_text=True
            )

        current_col = len(base_headers) + node_count * 2 + 1
        previous_col = current_col + 1
        planned_col = current_col + 2
        overdue_col = current_col + 4
        data_start = 4
        for row_index, row in enumerate(project['rows'], data_start):
            values = [
                row['project_name'], row['serial_no'], row['contract_no'],
                row['contract_title'], row['party_a'], row['party_b'],
                _minor_to_wan(row['serial_amount_minor']),
            ]
            for node_index in range(node_count):
                node = row['nodes'][node_index] if node_index < len(row['nodes']) else None
                values.extend([
                    _minor_to_wan(node['amount_minor']) if node else None,
                    node['condition'] if node else '',
                ])
            values.extend([
                _minor_to_wan(row['current_month_minor']),
                _minor_to_wan(row['previous_unpaid_minor']),
                None,
                row['payment_condition'],
                row['overdue_text'],
                row['bank_acceptance'],
                row['prior_unpaid_reason'],
            ])
            for column, value in enumerate(values, 1):
                cell = ws.cell(row_index, column, safe_spreadsheet_value(value))
                cell.font = _NORMAL_FONT
                cell.border = _THIN_BORDER
                cell.alignment = Alignment(
                    horizontal='right' if (
                        column == 7 or
                        8 <= column < current_col and column % 2 == 0 or
                        column in (current_col, previous_col, planned_col)
                    ) else 'left',
                    vertical='center',
                    wrap_text=True,
                )
            ws.cell(
                row_index, planned_col,
                f'={get_column_letter(current_col)}{row_index}+'
                f'{get_column_letter(previous_col)}{row_index}',
            )
            for column in [7, current_col, previous_col, planned_col]:
                ws.cell(row_index, column).number_format = '#,##0.00'
            for node_index, node in enumerate(row['nodes']):
                amount_col = 8 + node_index * 2
                condition_node_col = amount_col + 1
                ws.cell(row_index, amount_col).number_format = '#,##0.00'
                if node['is_paid']:
                    ws.cell(row_index, amount_col).fill = _PAID_FILL
                    ws.cell(row_index, condition_node_col).fill = _PAID_FILL
                elif node['is_current']:
                    ws.cell(row_index, amount_col).fill = _CURRENT_FILL
                    ws.cell(row_index, condition_node_col).fill = _CURRENT_FILL
            if row['current_month_minor']:
                ws.cell(row_index, current_col).fill = _CURRENT_FILL
            if row['previous_unpaid_minor']:
                ws.cell(row_index, previous_col).fill = _WARNING_FILL
                ws.cell(row_index, overdue_col).fill = _WARNING_FILL
            ws.row_dimensions[row_index].height = 42

        total_row = data_start + len(project['rows'])
        ws.cell(total_row, 1, '合计')
        ws.cell(total_row, 1).font = _HEADER_FONT
        for column in range(1, last_col + 1):
            cell = ws.cell(total_row, column)
            cell.border = _THIN_BORDER
            cell.fill = _HEADER_FILL
        numeric_cols = [7]
        numeric_cols.extend(8 + index * 2 for index in range(node_count))
        numeric_cols.extend([current_col, previous_col, planned_col])
        for column in numeric_cols:
            letter = get_column_letter(column)
            ws.cell(total_row, column, f'=SUM({letter}{data_start}:{letter}{total_row - 1})')
            ws.cell(total_row, column).number_format = '#,##0.00'
            ws.cell(total_row, column).font = _HEADER_FONT
        if not project['rows']:
            ws.cell(data_start, 1, '（本月无符合条件的数据）')

        widths = [18, 13, 18, 28, 22, 24, 14]
        for _ in range(node_count):
            widths.extend([14, 34])
        widths.extend([15, 18, 16, 38, 24, 16, 34])
        for column, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(column)].width = width
        _style_monthly_sheet(ws, last_col, total_row)
        ws.print_area = f'A1:{get_column_letter(last_col)}{total_row}'
        escaped_name = sheet_name.replace("'", "''")
        project_refs.append({
            'name': project['project_name'],
            'sheet_name': sheet_name,
            'sheet_formula_name': escaped_name,
            'current_cell': f'{get_column_letter(current_col)}{total_row}',
            'previous_cell': f'{get_column_letter(previous_col)}{total_row}',
            'planned_cell': f'{get_column_letter(planned_col)}{total_row}',
            'bank_value': _minor_to_wan(project['bank_acceptance_minor']) or 0,
        })

    summary_headers = [
        '项目', f'{display_month}计划付款合计', f'{display_month}计划付款',
        '以前月份计划未付款', '银行承兑支付金额', '说明',
    ]
    summary_ws.sheet_view.showGridLines = False
    summary_ws.merge_cells('A1:F1')
    summary_ws['A1'] = f'{display_month}合同付款计划汇总    单位：万元'
    summary_ws['A1'].font = _TITLE_FONT
    summary_ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    summary_ws.row_dimensions[1].height = 30
    for column, header in enumerate(summary_headers, 1):
        summary_ws.cell(3, column, header)
    _apply_header_style(summary_ws, 3, len(summary_headers))
    for cell in summary_ws[3]:
        cell.fill = PatternFill(
            start_color='4472C4', end_color='4472C4', fill_type='solid'
        )
        cell.font = Font(name='Microsoft YaHei', bold=True, color='FFFFFF')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for row_index, ref in enumerate(project_refs, 4):
        summary_ws.cell(row_index, 1, ref['name'])
        summary_ws.cell(
            row_index, 2,
            f"='{ref['sheet_formula_name']}'!{ref['planned_cell']}",
        )
        summary_ws.cell(
            row_index, 3,
            f"='{ref['sheet_formula_name']}'!{ref['current_cell']}",
        )
        summary_ws.cell(
            row_index, 4,
            f"='{ref['sheet_formula_name']}'!{ref['previous_cell']}",
        )
        summary_ws.cell(row_index, 5, ref['bank_value'])
        summary_ws.cell(row_index, 6, '')
        for column in range(1, 7):
            cell = summary_ws.cell(row_index, column)
            cell.border = _THIN_BORDER
            cell.font = _NORMAL_FONT
            if column in (2, 3, 4, 5):
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal='right')
    total_row = 4 + len(project_refs)
    summary_ws.cell(total_row, 1, '合计')
    for column in range(2, 6):
        if project_refs:
            letter = get_column_letter(column)
            summary_ws.cell(
                total_row, column,
                f'=SUM({letter}4:{letter}{total_row - 1})',
            )
        else:
            summary_ws.cell(total_row, column, 0)
        summary_ws.cell(total_row, column).number_format = '#,##0.00'
    for column in range(1, 7):
        cell = summary_ws.cell(total_row, column)
        cell.fill = _HEADER_FILL
        cell.border = _THIN_BORDER
        cell.font = _HEADER_FONT

    diagnostics = report.get('diagnostics') or {}
    messages = []
    labels = [
        ('unassigned_serial_count', '未关联合同内编号的付款计划'),
        ('missing_due_date_count', '缺少应付日期的付款计划'),
        ('missing_due_amount_count', '缺少应付金额的付款计划'),
        ('missing_serial_amount_count', '缺少本编号金额的报表行'),
    ]
    for key, label in labels:
        if diagnostics.get(key):
            messages.append(f"{label}：{diagnostics[key]}项")
    note_row = total_row + 2
    summary_ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=6)
    summary_ws.cell(
        note_row, 1,
        '数据检查：' + ('；'.join(messages) if messages else '未发现影响本报表的缺失项。'),
    )
    summary_ws.cell(note_row, 1).alignment = Alignment(wrap_text=True, vertical='center')
    summary_ws.cell(note_row, 1).fill = _WARNING_FILL if messages else _PAID_FILL
    summary_ws.row_dimensions[note_row].height = 34
    for column, width in enumerate([24, 20, 18, 22, 20, 34], 1):
        summary_ws.column_dimensions[get_column_letter(column)].width = width
    summary_ws.freeze_panes = 'A4'
    summary_ws.page_setup.orientation = 'landscape'
    summary_ws.sheet_properties.pageSetUpPr.fitToPage = True
    summary_ws.page_setup.fitToWidth = 1
    summary_ws.print_area = f'A1:F{note_row}'

    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = 'auto'
        wb.save(path)
    finally:
        wb.close()
    return path


def _export_contracts_streaming(path, contracts, title):
    """Write a large contract iterable without retaining worksheet cells."""
    headers = ['序号', '所属项目', '覆盖范围', '合同编号', '合同名称', '对方单位', '金额',
               '签订日期', '负责人', '状态', '创建时间', '付款计划数']
    col_widths = [6, 22, 16, 18, 26, 24, 14, 14, 14, 12, 14, 14]
    status_labels = {
        'draft': '草稿', 'signed': '已签订', 'active': '履行中',
        'completed': '已完成', 'void': '已作废',
    }
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title=title[:31])
    for ci, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = width

    title_cells = [
        WriteOnlyCell(ws, value=safe_spreadsheet_value(title))
    ] + [WriteOnlyCell(ws) for _ in headers[1:]]
    title_cells[0].font = _TITLE_FONT
    title_cells[0].alignment = Alignment(horizontal='center')
    ws.append(title_cells)
    ws.append([None] * len(headers))
    header_cells = []
    for header in headers:
        cell = WriteOnlyCell(ws, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = _THIN_BORDER
        header_cells.append(cell)
    ws.append(header_cells)

    total_amount = 0
    row_count = 0
    for row_count, contract in enumerate(contracts, 1):
        amount = _num(contract.get('amount'))
        total_amount += amount
        values = [
            row_count,
            contract.get('project_name') or '',
            (f"{contract.get('coverage_start')}–{contract.get('coverage_end')}号"
             if contract.get('coverage_start') is not None
             and contract.get('coverage_end') is not None else ''),
            contract.get('contract_no') or '',
            contract.get('title') or '',
            contract.get('counterparty') or '',
            amount,
            contract.get('sign_date') or '',
            contract.get('owner') or '',
            status_labels.get(contract.get('status'), contract.get('status', '')),
            (contract.get('created_at') or '')[:10],
            contract.get('plan_count', 0),
        ]
        cells = []
        for ci, value in enumerate(values, 1):
            cell = WriteOnlyCell(ws, value=safe_spreadsheet_value(value))
            cell.font = _NORMAL_FONT
            cell.border = _THIN_BORDER
            if ci == 7:
                cell.number_format = '#,##0.00'
            cells.append(cell)
        ws.append(cells)

    summary = ['合计' if row_count else '（无数据）', None, None, None, None, None,
               round(total_amount, 2) if row_count else None, None, None, None, None, None]
    summary_cells = []
    for ci, value in enumerate(summary, 1):
        cell = WriteOnlyCell(ws, value=value)
        cell.border = _THIN_BORDER
        if ci == 1:
            cell.font = _HEADER_FONT
        if ci == 7:
            cell.number_format = '#,##0.00'
        summary_cells.append(cell)
    ws.append(summary_cells)
    try:
        wb.save(path)
    finally:
        wb.close()
    return path


def export_contracts(path, contracts, title='合同台账', streaming=False):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    if streaming:
        return _export_contracts_streaming(path, contracts, title)
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
    title_cell = ws.cell(
        row=1, column=1, value=safe_spreadsheet_value(title)
    )
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
            cell = ws.cell(row=ri, column=ci, value=safe_spreadsheet_value(val))
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

    try:
        wb.save(path)
    finally:
        wb.close()
    return path


def _write_handover_table(wb, sheet_name, title, headers, rows, widths, money_cols=None):
    money_cols = set(money_cols or [])
    ws = wb.create_sheet(sheet_name[:31])
    col_count = len(headers)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
    title_cell = ws.cell(
        row=1, column=1, value=safe_spreadsheet_value(title)
    )
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='center')

    for ci, header in enumerate(headers, 1):
        ws.cell(row=3, column=ci, value=header)
    _apply_header_style(ws, 3, col_count)

    if rows:
        for ri, row in enumerate(rows, 4):
            for ci, value in enumerate(row, 1):
                cell = ws.cell(
                    row=ri, column=ci, value=safe_spreadsheet_value(value)
                )
                cell.font = _NORMAL_FONT
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                cell.border = _THIN_BORDER
                if ci in money_cols:
                    cell.number_format = '#,##0.00'
    else:
        ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=col_count)
        cell = ws.cell(row=4, column=1, value='（无数据）')
        cell.font = _NORMAL_FONT
        cell.alignment = Alignment(horizontal='center')
        for ci in range(1, col_count + 1):
            ws.cell(row=4, column=ci).border = _THIN_BORDER

    last_row = max(4, len(rows) + 3)
    ws.auto_filter.ref = f'A3:{get_column_letter(col_count)}{last_row}'
    ws.freeze_panes = 'A4'
    for ci, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = width
    return ws


def export_handover_checklist(path, data):
    """Export an employee handover checklist workbook."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = '交接总览'

    title = f"{data.get('owner', '')} 交接清单"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    title_cell = ws.cell(
        row=1, column=1, value=safe_spreadsheet_value(title)
    )
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='center')

    summary = data.get('summary') or {}
    overview_rows = [
        ('员工姓名', data.get('owner', '')),
        ('生成时间', data.get('generated_at', '')),
        ('数据范围', '包含已完成/已归档' if data.get('include_closed') else '未完成/未归档'),
        ('合同数量', summary.get('contract_count', 0)),
        ('付款计划数量', summary.get('payment_count', 0)),
        ('待付款金额', summary.get('outstanding_payment_amount', 0)),
        ('采购项目数量', summary.get('project_count', 0)),
        ('待处理采购数量', summary.get('active_project_count', 0)),
        ('风险/待办数量', summary.get('risk_count', 0)),
        ('文件数量', summary.get('file_count', 0)),
    ]
    ws.cell(row=3, column=1, value='项目')
    ws.cell(row=3, column=2, value='内容')
    _apply_header_style(ws, 3, 2)
    for ri, row in enumerate(overview_rows, 4):
        ws.cell(row=ri, column=1, value=row[0])
        ws.cell(row=ri, column=2, value=safe_spreadsheet_value(row[1]))
        for ci in (1, 2):
            cell = ws.cell(row=ri, column=ci)
            cell.font = _NORMAL_FONT
            cell.border = _THIN_BORDER
        if row[0] == '待付款金额':
            ws.cell(row=ri, column=2).number_format = '#,##0.00'
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 32

    contract_rows = []
    for idx, row in enumerate(data.get('contracts') or [], 1):
        contract_rows.append([
            idx,
            row.get('contract_no') or '',
            row.get('title') or '',
            row.get('counterparty') or '',
            row.get('amount') or 0,
            row.get('status_label') or '',
            row.get('sign_date') or '',
            row.get('expiry_date') or '',
            row.get('project_name') or '',
            row.get('plan_count') or 0,
            row.get('unpaid_plan_count') or 0,
            row.get('unpaid_amount') or 0,
            row.get('docx_path') or '',
        ])
    _write_handover_table(
        wb,
        '合同清单',
        '合同清单',
        ['序号', '合同编号', '合同名称', '对方单位', '金额', '状态', '签订日期',
         '到期日期', '所属项目', '付款计划数', '未完成付款数', '待付款金额', '文件路径'],
        contract_rows,
        [6, 18, 28, 24, 14, 12, 13, 13, 22, 12, 14, 14, 42],
        money_cols={5, 12},
    )

    payment_rows = []
    for idx, row in enumerate(data.get('payments') or [], 1):
        payment_rows.append([
            idx,
            row.get('contract_no') or '',
            row.get('contract_title') or '',
            row.get('phase_name') or '',
            row.get('due_date') or '',
            row.get('due_amount') or 0,
            row.get('paid_amount') or 0,
            row.get('unpaid_amount') or 0,
            row.get('confirm_status_label') or '',
            row.get('payment_status_label') or '',
            row.get('condition_text') or '',
            row.get('project_name') or '',
        ])
    _write_handover_table(
        wb,
        '付款计划',
        '付款计划',
        ['序号', '合同编号', '合同名称', '阶段', '应付日期', '应付金额', '已付金额',
         '未付金额', '确认状态', '付款状态', '付款条件', '所属项目'],
        payment_rows,
        [6, 18, 28, 18, 13, 14, 14, 14, 12, 12, 40, 22],
        money_cols={6, 7, 8},
    )

    project_rows = []
    for idx, row in enumerate(data.get('projects') or [], 1):
        project_rows.append([
            idx,
            row.get('project_no') or '',
            row.get('project_name') or '',
            row.get('status_label') or '',
            row.get('method_label') or '',
            row.get('demand_department') or '',
            row.get('budget_amount') or 0,
            row.get('target_price_amount') or 0,
            row.get('item_count') or 0,
            row.get('supplier_count') or 0,
            row.get('quote_count') or 0,
            row.get('pending_clarification_count') or 0,
            row.get('updated_at') or '',
        ])
    _write_handover_table(
        wb,
        '采购项目',
        '采购项目',
        ['序号', '项目编号', '项目名称', '状态', '采购方式', '需求部门', '预算金额',
         '限价金额', '明细数', '供应商数', '报价数', '未关闭澄清', '更新时间'],
        project_rows,
        [6, 18, 28, 14, 18, 18, 14, 14, 10, 10, 10, 12, 20],
        money_cols={7, 8},
    )

    risk_rows = []
    for idx, row in enumerate(data.get('risks') or [], 1):
        risk_rows.append([
            idx,
            row.get('risk_type') or '',
            row.get('related_no') or '',
            row.get('related_name') or '',
            row.get('detail') or '',
            row.get('amount') if row.get('amount') != '' else '',
            row.get('due_date') or '',
            row.get('status') or '',
        ])
    _write_handover_table(
        wb,
        '待办风险',
        '待办风险',
        ['序号', '类型', '编号', '名称', '说明', '金额', '日期', '状态'],
        risk_rows,
        [6, 14, 18, 28, 40, 14, 13, 14],
        money_cols={6},
    )

    file_rows = []
    for idx, row in enumerate(data.get('files') or [], 1):
        file_rows.append([
            idx,
            row.get('source') or '',
            row.get('related_no') or '',
            row.get('related_name') or '',
            row.get('file_type') or '',
            row.get('original_name') or '',
            row.get('relative_path') or '',
            row.get('size_bytes') or '',
            row.get('created_at') or '',
        ])
    _write_handover_table(
        wb,
        '文件清单',
        '文件清单',
        ['序号', '来源', '关联编号', '关联名称', '类型', '原始文件名', '相对路径',
         '大小(Byte)', '创建时间'],
        file_rows,
        [6, 12, 18, 28, 14, 24, 48, 14, 20],
    )

    try:
        wb.save(path)
    finally:
        wb.close()
    return path
