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
    ContractStatus.DRAFT: '草稿',
    ContractStatus.SIGNED: '已签订',
    ContractStatus.ACTIVE: '履行中',
    ContractStatus.COMPLETED: '已完成',
    ContractStatus.VOID: '已作废',
}

CONFIRM_STATUS_LABELS = {
    ConfirmStatus.PENDING: '待确认',
    ConfirmStatus.CONFIRMED: '已确认',
    ConfirmStatus.VOID: '已作废',
}

PAYMENT_STATUS_LABELS = {
    PaymentStatus.UNPAID: '未付款',
    PaymentStatus.PARTIAL: '部分付款',
    PaymentStatus.PAID: '已付款',
}

CONFIDENCE_LABELS = {
    ConfidenceLevel.HIGH: '高',
    ConfidenceLevel.MEDIUM: '中',
    ConfidenceLevel.LOW: '低',
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
