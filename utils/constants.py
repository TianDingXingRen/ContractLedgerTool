"""枚举常量 — 替代散落全项目的硬编码字符串"""

from enum import Enum


class FieldType(str, Enum):
    """模板字段类型"""
    TEXT = 'text'
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
