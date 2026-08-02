"""Semantic parser for one tokenized payment clause."""

from __future__ import annotations

import re
from dataclasses import dataclass

from payment_extraction.tokenizer import (
    detect_amount_basis,
    extract_amounts,
    extract_date,
    extract_days,
    extract_ratios,
)


EVENT_LABELS = {
    'contract_signed': '合同签订',
    'effective': '合同生效',
    'invoice_received': '收到发票',
    'arrival': '到货',
    'shipment': '发货',
    'delivery': '交付',
    'acceptance': '验收合格',
    'warranty_end': '质保期满',
    'production_notice_issued': '投产通知下达',
    'settlement_confirmed': '结算确认',
    'fixed_date': '固定日期',
    'other': '其他',
}

EVENT_PATTERNS = (
    ('production_notice_issued', r'(?:收到|接到|下达|签收|确认)?(?:投产|生产|排产)通知'),
    ('contract_signed', r'(?:合同)?(?:签订|签署|盖章)'),
    ('effective', r'合同生效|生效'),
    ('invoice_received', r'收到[^，；。]{0,16}发票|发票(?:开具|送达|提交)|开票'),
    ('acceptance', r'(?:验收合格|通过验收|终验|初验)'),
    ('arrival', r'(?:货到|到货)'),
    ('shipment', r'发货'),
    ('delivery', r'交付'),
    ('warranty_end', r'(?:质保期|保修期)(?:届满|期满|满)'),
    ('settlement_confirmed', r'(?:结算|对账)(?:完成|确认|审核)'),
)

REPEAT_KEYWORDS = ('每次', '每批', '各批', '各批次', '逐批', '每份通知', '每一批')


@dataclass(frozen=True)
class ParsedPaymentNode:
    """Semantic values parsed from one clause, before monetary resolution."""

    segment: str
    ratios: list[float]
    amounts: list[float]
    explicit_date: str
    conditions: list[dict]
    trigger_days: int | None
    amount_basis: str
    amount_basis_text: str
    repeat_mode: str
    scope: str
    condition_logic: str
    reasons: list[str]


def parse_payment_node(segment, sign_date=''):
    ratios = extract_ratios(segment)
    amounts = extract_amounts(segment)
    explicit_date = extract_date(segment, sign_date)
    conditions = detect_conditions(segment, explicit_date)
    trigger_days = extract_days(segment)
    basis, basis_text = detect_amount_basis(segment)
    repeat_mode = (
        'each_event' if is_recurring(segment, basis, conditions) else 'once'
    )
    scope = scope_for_rule(repeat_mode, basis, conditions)
    reasons = []

    if len(ratios) > 1:
        reasons.append('NODE_BOUNDARY_AMBIGUOUS')
    if not ratios and not amounts:
        reasons.append('AMOUNT_MISSING')
    if not conditions and not explicit_date:
        reasons.append('TRIGGER_MISSING')

    logic = condition_logic(segment, conditions)
    if len(conditions) > 1 and logic == 'OTHER':
        reasons.append('CONDITION_LOGIC_AMBIGUOUS')
    if basis == 'unknown' and repeat_mode == 'each_event':
        reasons.append('AMOUNT_BASIS_MISSING')

    return ParsedPaymentNode(
        segment=segment,
        ratios=ratios,
        amounts=amounts,
        explicit_date=explicit_date,
        conditions=conditions,
        trigger_days=trigger_days,
        amount_basis=basis,
        amount_basis_text=basis_text,
        repeat_mode=repeat_mode,
        scope=scope,
        condition_logic=logic,
        reasons=reasons,
    )


def detect_conditions(text, explicit_date=''):
    found = []
    for code, pattern in EVENT_PATTERNS:
        match = re.search(pattern, text)
        if match:
            found.append({'code': code, 'start': match.start(), 'end': match.end()})
    found.sort(key=lambda item: item['start'])
    if not found and explicit_date:
        found.append({'code': 'fixed_date', 'start': 0, 'end': 0})
    return found


def condition_logic(text, conditions):
    if len(conditions) <= 1:
        return 'SINGLE'
    connectors = []
    for left, right in zip(conditions, conditions[1:]):
        connectors.append(text[left['end']:right['start']])
    joined = ''.join(connectors)
    if any(word in joined for word in ('或', '任一')):
        return 'OR'
    if any(word in joined for word in ('且', '并', '及', '同时', '和')):
        return 'AND'
    return 'OTHER'


def condition_label(conditions, logic, explicit_date):
    if not conditions:
        return EVENT_LABELS['fixed_date'] if explicit_date else EVENT_LABELS['other']
    labels = [EVENT_LABELS.get(item['code'], item['code']) for item in conditions]
    connector = {'AND': '且', 'OR': '或'}.get(logic, '、')
    return connector.join(labels)


def detect_event(text, explicit_date=''):
    conditions = detect_conditions(text, explicit_date)
    return conditions[0]['code'] if conditions else 'other'


def is_recurring(text, basis, conditions):
    event_codes = {item['code'] for item in conditions}
    recurring_scope = basis in {'production_notice_total', 'batch_delivery_total'}
    recurring_event = 'production_notice_issued' in event_codes
    return any(keyword in text for keyword in REPEAT_KEYWORDS) and (
        recurring_scope or recurring_event
    )


def scope_for_rule(repeat_mode, basis, conditions):
    event_codes = {item['code'] for item in conditions}
    if basis == 'production_notice_total' or 'production_notice_issued' in event_codes:
        return 'production_notice'
    if basis == 'batch_delivery_total':
        return 'delivery_batch'
    if basis == 'settlement_amount':
        return 'settlement_period'
    return 'contract' if repeat_mode == 'once' else 'other'


def phase_name(text, index):
    if '预付款' in text or '预付' in text or '定金' in text:
        return '预付款'
    if '投产通知' in text or '生产通知' in text or '排产通知' in text:
        return '投产通知款'
    if '到货' in text or '货到' in text:
        return '到货款'
    if '验收' in text:
        return '验收款'
    if '质保' in text:
        return '质保金'
    if '尾款' in text or '余款' in text:
        return '尾款'
    if '进度' in text:
        return '进度款'
    if index:
        return f'第{index + 1}期款'
    return '付款'
