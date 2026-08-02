"""Declarative column definitions shared by XLSX exporters."""

from __future__ import annotations

from dataclasses import dataclass


MONEY_FORMAT = '#,##0.00'


@dataclass(frozen=True)
class ColumnDefinition:
    header: str
    width: float
    number_format: str | None = None


def column_headers(columns):
    return [column.header for column in columns]


def column_widths(columns):
    return [column.width for column in columns]


def money_column_numbers(columns):
    """Return one-based indexes for columns using the money format."""
    return {
        index
        for index, column in enumerate(columns, start=1)
        if column.number_format == MONEY_FORMAT
    }


PAYMENT_PLAN_COLUMNS = (
    ColumnDefinition('序号', 6),
    ColumnDefinition('所属项目', 22),
    ColumnDefinition('覆盖范围', 16),
    ColumnDefinition('合同编号', 18),
    ColumnDefinition('合同名称', 26),
    ColumnDefinition('对方单位', 24),
    ColumnDefinition('款项名称', 16),
    ColumnDefinition('应付日期', 14),
    ColumnDefinition('应付金额', 14, MONEY_FORMAT),
    ColumnDefinition('已付金额', 14, MONEY_FORMAT),
    ColumnDefinition('未付金额', 14, MONEY_FORMAT),
    ColumnDefinition('付款条件', 36),
    ColumnDefinition('负责人', 14),
    ColumnDefinition('备注', 24),
)

CONTRACT_COLUMNS = (
    ColumnDefinition('序号', 6),
    ColumnDefinition('所属项目', 22),
    ColumnDefinition('覆盖范围', 16),
    ColumnDefinition('合同编号', 18),
    ColumnDefinition('合同名称', 26),
    ColumnDefinition('对方单位', 24),
    ColumnDefinition('金额', 14, MONEY_FORMAT),
    ColumnDefinition('签订日期', 14),
    ColumnDefinition('负责人', 14),
    ColumnDefinition('状态', 12),
    ColumnDefinition('创建时间', 14),
    ColumnDefinition('付款计划数', 14),
)

MONTHLY_BASE_COLUMNS = (
    ColumnDefinition('火箭发次\n（项目名称）', 15.83203125),
    ColumnDefinition('合同编号', 12.08203125),
    ColumnDefinition('合同名称', 10.25),
    ColumnDefinition('甲方', 7.75),
    ColumnDefinition('乙方\n（全称）', 13.08203125),
    ColumnDefinition('合同额', 9.5, MONEY_FORMAT),
)

MONTHLY_TAIL_COLUMNS = (
    ColumnDefinition('本次付款', 14.33203125, MONEY_FORMAT),
    ColumnDefinition('合同约定本次付款需满足条件', 32.75),
    ColumnDefinition(
        '超过合同付款时间\n（超过应该付款的期限）',
        25.08203125,
    ),
    ColumnDefinition('银行承兑', 23.6640625),
    ColumnDefinition('上月已做计划未付款说明', 23.6640625),
)

MONTHLY_SUMMARY_COLUMNS = (
    ColumnDefinition('项目', 21.75),
    ColumnDefinition('{month}计划付款合计', 28.08203125, MONEY_FORMAT),
    ColumnDefinition('本月计划付款', 22.08203125, MONEY_FORMAT),
    ColumnDefinition('上月已做计划未付款', 27.58203125, MONEY_FORMAT),
    ColumnDefinition('可用银行承兑支付金额', 27.58203125, MONEY_FORMAT),
    ColumnDefinition('说明', 41.75),
)

HANDOVER_OVERVIEW_COLUMNS = (
    ColumnDefinition('项目', 18),
    ColumnDefinition('内容', 32),
)

HANDOVER_TABLE_COLUMNS = {
    'contracts': (
        ColumnDefinition('序号', 6),
        ColumnDefinition('合同编号', 18),
        ColumnDefinition('合同名称', 28),
        ColumnDefinition('对方单位', 24),
        ColumnDefinition('金额', 14, MONEY_FORMAT),
        ColumnDefinition('状态', 12),
        ColumnDefinition('签订日期', 13),
        ColumnDefinition('到期日期', 13),
        ColumnDefinition('所属项目', 22),
        ColumnDefinition('付款计划数', 12),
        ColumnDefinition('未完成付款数', 14),
        ColumnDefinition('待付款金额', 14, MONEY_FORMAT),
        ColumnDefinition('文件路径', 42),
    ),
    'payments': (
        ColumnDefinition('序号', 6),
        ColumnDefinition('合同编号', 18),
        ColumnDefinition('合同名称', 28),
        ColumnDefinition('阶段', 18),
        ColumnDefinition('应付日期', 13),
        ColumnDefinition('应付金额', 14, MONEY_FORMAT),
        ColumnDefinition('已付金额', 14, MONEY_FORMAT),
        ColumnDefinition('未付金额', 14, MONEY_FORMAT),
        ColumnDefinition('确认状态', 12),
        ColumnDefinition('付款状态', 12),
        ColumnDefinition('付款条件', 40),
        ColumnDefinition('所属项目', 22),
    ),
    'projects': (
        ColumnDefinition('序号', 6),
        ColumnDefinition('项目编号', 18),
        ColumnDefinition('项目名称', 28),
        ColumnDefinition('状态', 14),
        ColumnDefinition('采购方式', 18),
        ColumnDefinition('需求部门', 18),
        ColumnDefinition('预算金额', 14, MONEY_FORMAT),
        ColumnDefinition('限价金额', 14, MONEY_FORMAT),
        ColumnDefinition('明细数', 10),
        ColumnDefinition('供应商数', 10),
        ColumnDefinition('报价数', 10),
        ColumnDefinition('未关闭澄清', 12),
        ColumnDefinition('更新时间', 20),
    ),
    'risks': (
        ColumnDefinition('序号', 6),
        ColumnDefinition('类型', 14),
        ColumnDefinition('编号', 18),
        ColumnDefinition('名称', 28),
        ColumnDefinition('说明', 40),
        ColumnDefinition('金额', 14, MONEY_FORMAT),
        ColumnDefinition('日期', 13),
        ColumnDefinition('状态', 14),
    ),
    'files': (
        ColumnDefinition('序号', 6),
        ColumnDefinition('来源', 12),
        ColumnDefinition('关联编号', 18),
        ColumnDefinition('关联名称', 28),
        ColumnDefinition('类型', 14),
        ColumnDefinition('原始文件名', 24),
        ColumnDefinition('相对路径', 48),
        ColumnDefinition('大小(Byte)', 14),
        ColumnDefinition('创建时间', 20),
    ),
}


def monthly_detail_columns(node_count):
    columns = list(MONTHLY_BASE_COLUMNS)
    for node_index in range(1, node_count + 1):
        columns.extend((
            ColumnDefinition(
                f'付款节点#{node_index}\n（金额）',
                14.08203125,
                MONEY_FORMAT,
            ),
            ColumnDefinition(
                f'付款节点#{node_index}\n（预期时间+支付条件）',
                26.33203125 if node_index <= 2 else 21.58203125,
            ),
        ))
    columns.extend(MONTHLY_TAIL_COLUMNS)
    return tuple(columns)


def monthly_summary_columns(display_month):
    return tuple(
        ColumnDefinition(
            column.header.format(month=display_month),
            column.width,
            column.number_format,
        )
        for column in MONTHLY_SUMMARY_COLUMNS
    )
