"""合同字段关键词映射：将中文标签/字段名与业务含义关联，用于自动匹配。

本模块替代 award_service.py 和 generation_utils.py 中分散的硬编码关键词匹配逻辑。
所有映射关系集中维护，便于调整和复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


# ═══════════════════════════════════════════════════════
#  字段关键词 → 业务语义 映射表
# ═══════════════════════════════════════════════════════

@dataclass
class FieldMatcher:
    """将中英文关键词关联到合同/采购相关的业务语义。"""

    keywords: list[str]
    """用于匹配的中英文关键词列表，匹配时忽略大小写。"""

    description: str = ''
    """该匹配器的业务含义描述。"""


# ── 标量字段匹配 ──

SCALAR_FIELD_MATCHERS: list[tuple[str, FieldMatcher]] = [
    ('contract_no', FieldMatcher(['合同编号', '合同号', 'contract_no'], '合同编号')),
    ('project_no', FieldMatcher(['项目编号', 'project_no'], '项目编号')),
    ('title', FieldMatcher(['项目名称', '合同名称', '标题', 'project_name', 'title'], '合同/项目名称')),
    ('counterparty', FieldMatcher([
        '供应商', '对方', '乙方', '供方', '卖方', '客户', '对方单位', '对方名称',
        '乙方单位名称', '乙方名称', 'counterparty',
    ], '对方单位/供应商')),
    ('amount', FieldMatcher([
        '合同金额', '总金额', '合同总价', '成交金额', '价款', '金额', '合计',
        'amount', 'total',
    ], '合同金额')),
    ('sign_date', FieldMatcher([
        '签订日期', '签约日期', '签署日期', '日期', 'sign_date',
    ], '签订日期')),
    ('owner', FieldMatcher(['经办人', '负责人', '业务员', 'owner'], '经办人/负责人')),
    ('demand_department', FieldMatcher(['需求部门', '部门', 'department'], '需求部门')),
    ('delivery_place', FieldMatcher(['交付地点', 'delivery_place'], '交付地点')),
    ('delivery_terms', FieldMatcher(['交付周期', '交期', '交付条件', 'delivery'], '交付条款')),
    ('payment_terms', FieldMatcher(['付款条件', '付款方式', '付款要求', 'payment'], '付款条件')),
    ('warranty', FieldMatcher(['质保', '质保期', 'warranty'], '质保信息')),
    ('technical_notes', FieldMatcher(['技术要求', '技术说明', '技术偏离', 'technical'], '技术要求/说明')),
    ('commercial_notes', FieldMatcher(['商务偏离', '商务说明', '商业条款', 'commercial'], '商务说明')),
    ('contract_notice', FieldMatcher(['注意事项', '合同备注', '合同说明', 'contract_notice'], '合同注意事项')),
]

# ── 表格列字段匹配 ──

TABLE_COLUMN_MATCHERS: list[tuple[str, FieldMatcher]] = [
    ('line_no', FieldMatcher(['序号', '序', '编号', 'line_no', 'index', 'no', 'number'], '行号')),
    ('item_name', FieldMatcher(['物资名称', '产品名称', '标的名称', 'item_name', 'product_name'], '物资/产品名称')),
    ('supplier', FieldMatcher(['供应商', '供方', 'supplier'], '供应商')),
    ('spec_model', FieldMatcher(['规格', '型号', '规格型号', 'spec', 'model'], '规格型号')),
    ('drawing_no', FieldMatcher(['图号', 'drawing_no'], '图号')),
    ('quantity', FieldMatcher(['数量', 'qty', 'quantity'], '数量')),
    ('unit', FieldMatcher(['单位', '计量单位', 'unit', 'uom'], '单位')),
    ('unit_price', FieldMatcher(['单价', 'unit_price'], '单价')),
    ('amount', FieldMatcher(['小计', '合计', '金额', '总价', 'subtotal', 'amount'], '金额/小计')),
    ('remark', FieldMatcher(['备注', '说明', 'remark', 'note'], '备注')),
    ('tax_rate', FieldMatcher(['税率', 'tax_rate'], '税率')),
    ('tax_amount', FieldMatcher(['税额', 'tax_amount'], '税额')),
]

# ── 批量匹配对方单位的关键词 ──

BATCH_COUNTERPARTY_KEYWORDS: list[str] = [
    '对方单位', '对方名称', '供应商', '供方', '卖方',
    '乙方单位名称', '乙方名称', '乙方', '对方', '客户名称', 'counterparty',
]

# ── 合同编号字段关键词 ──

CONTRACT_NUMBER_KEYWORDS: list[str] = [
    '合同编号', '合同号', 'contract_no',
]


def _make_lookup(matchers: list[tuple[str, FieldMatcher]]) -> Callable[[str, str], Optional[str]]:
    """基于匹配器列表构建查找函数。

    返回一个 (label, key) → 第一个匹配的语义标识 的函数。
    若 label 以关键词开头且关键词长度 >= 3 才视为匹配，避免误匹配短词。
    """
    flat: list[tuple[str, list[str]]] = []
    for semantic_id, matcher in matchers:
        for keyword in matcher.keywords:
            flat.append((semantic_id, keyword))

    flat.sort(key=lambda item: -len(item[1]))

    def lookup(label: str, key: str) -> Optional[str]:
        haystack = f'{label or ""} {key or ""}'.lower()
        for semantic_id, keyword in flat:
            if keyword.lower() in haystack:
                return semantic_id
        return None

    return lookup


find_scalar_semantic = _make_lookup(SCALAR_FIELD_MATCHERS)
find_column_semantic = _make_lookup(TABLE_COLUMN_MATCHERS)


def contains_keyword(text: str, *keywords: str) -> bool:
    """检查文本是否包含任一关键词（不区分大小写）。"""
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)
