"""枚举常量 — 替代散落全项目的硬编码字符串"""

from enum import Enum


class FieldType(str, Enum):
    """模板字段类型"""
    TEXT = 'text'
    NUMBER = 'number'
    TEXTAREA = 'textarea'
    SELECT = 'select'
    TABLE = 'table'
    CALCULATED = 'calculated'


class ContractStatus(str, Enum):
    """合同状态"""
    DRAFT = 'draft'
    SIGNED = 'signed'
    ACTIVE = 'active'
    COMPLETED = 'completed'
    VOID = 'void'


class ConfirmStatus(str, Enum):
    """付款计划确认状态"""
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    VOID = 'void'


class PaymentStatus(str, Enum):
    """付款状态"""
    UNPAID = 'unpaid'
    PARTIAL = 'partial'
    PAID = 'paid'


class ConfidenceLevel(str, Enum):
    """付款计划置信度"""
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


# ── 标签映射 ──

CONTRACT_STATUS_LABELS = {
    ContractStatus.DRAFT.value: '草稿',
    ContractStatus.SIGNED.value: '已签订',
    ContractStatus.ACTIVE.value: '履行中',
    ContractStatus.COMPLETED.value: '已完成',
    ContractStatus.VOID.value: '已作废',
}

CONFIRM_STATUS_LABELS = {
    ConfirmStatus.PENDING.value: '待确认',
    ConfirmStatus.CONFIRMED.value: '已确认',
    ConfirmStatus.VOID.value: '已作废',
}

PAYMENT_STATUS_LABELS = {
    PaymentStatus.UNPAID.value: '未付款',
    PaymentStatus.PARTIAL.value: '部分付款',
    PaymentStatus.PAID.value: '已付款',
}

CONFIDENCE_LABELS = {
    ConfidenceLevel.HIGH.value: '高',
    ConfidenceLevel.MEDIUM.value: '中',
    ConfidenceLevel.LOW.value: '低',
}

PAYMENT_PARSE_STATUS_LABELS = {
    'exact': '完整匹配',
    'partial': '需要补充',
    'conflict': '存在冲突',
    'unsupported': '暂不支持',
    'manual': '人工录入',
}

PAYMENT_REASON_LABELS = {
    'AMOUNT_MISSING': '未识别到付款金额或比例',
    'TRIGGER_MISSING': '未识别到付款触发条件',
    'AMOUNT_BASIS_MISSING': '付款金额计算基数不明确',
    'AMOUNT_BASIS_INFERRED': '计算基数根据合同上下文推定',
    'EXPLICIT_AMOUNT_MISMATCH': '合同明确金额与比例计算金额不一致',
    'MULTIPLE_CONDITIONS_AMBIGUOUS': '存在多个触发条件，关系不明确',
    'CONDITION_LOGIC_AMBIGUOUS': '多个触发条件之间的逻辑关系不明确',
    'NODE_BOUNDARY_AMBIGUOUS': '同一节点包含多个比例，节点边界需要核对',
    'RATIO_SUM_EXCEEDS_100': '同一规则组的付款比例合计超过100%',
}

PAYMENT_AMOUNT_BASIS_LABELS = {
    'unknown': '计算基数未明确',
    'contract_total_tax_inclusive': '合同总价（含税）',
    'contract_total_tax_exclusive': '合同总价（不含税）',
    'production_notice_total': '本次投产通知产品总价',
    'batch_delivery_total': '本批次产品总价',
    'accepted_product_total': '验收合格产品总价',
    'settlement_amount': '当期结算金额',
    'invoice_amount': '发票金额',
    'remaining_contract_amount': '合同剩余金额',
}


# ── 采购流程标签与阶段配置 ──

PROCUREMENT_STATUS_LABELS = {
    'draft': '草稿',
    'documents_ready': '询价文件已准备',
    'inquiry_sent': '已发询价',
    'quotes_received': '已收报价',
    'clarifying': '澄清中',
    'negotiating': '谈判中',
    'award_draft': '成交建议中',
    'award_confirmed': '成交已确认',
    'contract_draft': '合同数据单',
    'contract_created': '合同已生成',
    'archived': '已归档',
}

PROCUREMENT_METHOD_LABELS = {
    'competitive_negotiation': '竞争性谈判',
    'inquiry': '询价',
    'comparison': '比价',
    'single_source': '单一来源',
}

PROCUREMENT_STAGE_ORDER = [
    'project',
    'items',
    'suppliers',
    'quotes',
    'comparison',
    'negotiation',
    'award',
    'contract',
    'archive',
]

PROCUREMENT_STAGE_LABELS = {
    'project': '项目基础信息',
    'items': '采购明细',
    'suppliers': '候选供应商',
    'quotes': '供应商报价',
    'comparison': '比价与澄清',
    'negotiation': '谈判记录',
    'award': '成交建议',
    'contract': '合同生成',
    'archive': '项目归档',
}

PROCUREMENT_STAGE_STATUS_LABELS = {
    'done': '已完成',
    'active': '推荐下一步',
    'skipped': '已跳过',
    'available': '可切入',
    'blocked': '待补录',
    'not_applicable': '不适用',
}

CLARIFICATION_STATUS_LABELS = {
    'pending': '待处理',
    'confirmed': '已确认',
    'sent': '已发出',
    'replied': '已回复',
    'closed': '已关闭',
}

QUOTE_STATUS_LABELS = {
    'pending': '待报价',
    'received': '已收报价',
    'confirmed': '已确认',
    'superseded': '已被覆盖',
    'rejected': '已拒绝',
}

QUOTE_IMPORT_STATUS_LABELS = {
    'mapping': '待映射',
    'parsed': '已解析',
    'invalid': '解析异常',
    'confirmed': '已导入',
    'cancelled': '已取消',
}
