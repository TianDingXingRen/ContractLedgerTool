"""Resolution layer for parsed payment nodes."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from payment_extraction.parser import (
    EVENT_LABELS,
    condition_label,
    parse_payment_node,
    phase_name,
)
from payment_extraction.tokenizer import looks_like_price_summary


MAX_EXTRACTED_PLANS = 30
MAX_EXTRACTED_RULES = 60
EXTRACTOR_VERSION = 'payment-rules-v2'


@dataclass(frozen=True)
class PaymentExtractionResult:
    plans: list[dict]
    rules: list[dict]
    warnings: list[str]


def resolve_rule(segment, contract_amount, sign_date, group_key, ordinal, block):
    node = parse_payment_node(segment, sign_date)
    basis = node.amount_basis
    basis_text = node.amount_basis_text
    reasons = list(node.reasons)

    if basis == 'unknown' and node.ratios and contract_amount is not None:
        basis = 'contract_total_tax_inclusive'
        basis_text = '合同金额（根据上下文推定）'
        reasons.append('AMOUNT_BASIS_INFERRED')

    ratio_values = node.ratios or [None]
    rule_plans = []
    rules_for_node = []
    for ratio_index, ratio in enumerate(ratio_values):
        explicit_amount = paired_amount(
            node.amounts, ratio_index, len(ratio_values)
        )
        calculated_amount = calculated_amount_for(
            ratio, basis, contract_amount
        )
        conflict = amounts_conflict(explicit_amount, calculated_amount)
        item_reasons = list(reasons)
        if conflict:
            item_reasons.append('EXPLICIT_AMOUNT_MISMATCH')
        status = parse_status(item_reasons)
        due_amount = None if conflict else (
            explicit_amount
            if explicit_amount is not None
            else calculated_amount
        )
        event_codes = [item['code'] for item in node.conditions]
        trigger_event = condition_label(
            node.conditions, node.condition_logic, node.explicit_date
        )
        due_date = node.explicit_date
        legacy_event = (
            event_codes[0]
            if event_codes
            else ('fixed_date' if node.explicit_date else 'other')
        )
        if (
            not due_date
            and sign_date
            and legacy_event in ('contract_signed', 'effective')
        ):
            due_date = add_days(sign_date, node.trigger_days or 0)
        rule_fingerprint = fingerprint(
            f'{group_key}|{ordinal}|{ratio_index}|{segment}|{ratio}|'
            f'{explicit_amount}|{basis}|{node.repeat_mode}'
        )
        payment_phase_name = phase_name(segment, ratio_index)
        rule = {
            'group_key': group_key,
            'phase_name': payment_phase_name,
            'rule_type': (
                'recurring'
                if node.repeat_mode == 'each_event'
                else 'conditional'
            ),
            'scope': node.scope,
            'trigger_event_type': legacy_event,
            'trigger_event': trigger_event,
            'trigger_days': node.trigger_days,
            'due_date': due_date,
            'conditions': event_codes,
            'conditions_json': json.dumps(event_codes, ensure_ascii=False),
            'condition_logic': node.condition_logic,
            'amount_basis': basis,
            'amount_basis_text': basis_text,
            'ratio': ratio,
            'explicit_amount': explicit_amount,
            'calculated_amount': calculated_amount,
            'repeat_mode': node.repeat_mode,
            'source_text': segment,
            'source_block': block_label(block),
            'rule_fingerprint': rule_fingerprint,
            'source_fingerprint': fingerprint(segment),
            'extractor_version': EXTRACTOR_VERSION,
            'rule_version': 1,
            'parse_status': status,
            'reason_codes': item_reasons,
            'reason_codes_json': json.dumps(item_reasons, ensure_ascii=False),
            'confirm_status': 'pending',
            'user_modified': 0,
        }
        rules_for_node.append(rule)
        if node.repeat_mode == 'once' and status not in ('conflict', 'unsupported'):
            if ratio is not None or due_amount is not None:
                plan = make_plan(
                    segment=segment,
                    phase_name=payment_phase_name,
                    trigger_event=legacy_event,
                    trigger_days=node.trigger_days,
                    due_date=due_date,
                    ratio=ratio,
                    due_amount=due_amount,
                    confidence=status_confidence(status),
                )
                plan.update({
                    'trigger_event': trigger_event,
                    'amount_basis': basis,
                    'amount_basis_text': basis_text,
                    'explicit_amount': explicit_amount,
                    'calculated_amount': calculated_amount,
                    'conditions_json': rule['conditions_json'],
                    'condition_logic': node.condition_logic,
                    'repeat_mode': node.repeat_mode,
                    'parse_status': status,
                    'reason_codes_json': rule['reason_codes_json'],
                    'rule_fingerprint': rule_fingerprint,
                    'extractor_version': EXTRACTOR_VERSION,
                    'user_modified': 0,
                })
                rule_plans.append(plan)
    return rules_for_node, rule_plans


def parse_segment(segment, contract_amount, sign_date):
    """Legacy private API retained for existing callers and tests."""
    parsed = resolve_rule(
        segment,
        contract_amount,
        sign_date,
        group_key=fingerprint(segment),
        ordinal=0,
        block={'kind': 'paragraph', 'index': 1, 'text': segment},
    )
    return parsed[1] if parsed else []


def make_plan(
    segment,
    phase_name,
    trigger_event,
    trigger_days,
    due_date,
    ratio,
    due_amount,
    confidence,
):
    payment_type = (
        'fixed_date'
        if due_date and trigger_event == 'fixed_date'
        else 'conditional'
    )
    return {
        'phase_name': phase_name,
        'payment_type': payment_type,
        'trigger_event': EVENT_LABELS.get(trigger_event, '其他'),
        'trigger_days': trigger_days,
        'due_date': due_date,
        'ratio': ratio,
        'due_amount': due_amount,
        'paid_amount': 0,
        'condition_text': segment,
        'source_text': segment,
        'confidence': confidence,
        'confirm_status': 'pending',
        'payment_status': 'unpaid',
    }


def paired_amount(amounts, index, ratio_count):
    if not amounts:
        return None
    if ratio_count == 1:
        return amounts[-1]
    if len(amounts) == ratio_count:
        return amounts[index]
    return None


def calculated_amount_for(ratio, basis, contract_amount):
    if ratio is None or contract_amount is None:
        return None
    if basis not in {
        'contract_total_tax_inclusive',
        'contract_total_tax_exclusive',
    }:
        return None
    try:
        return round(float(contract_amount) * float(ratio) / 100, 2)
    except (TypeError, ValueError, OverflowError):
        return None


def amounts_conflict(explicit_amount, calculated_amount):
    if explicit_amount is None or calculated_amount is None:
        return False
    tolerance = max(1.0, abs(calculated_amount) * 0.01)
    return abs(explicit_amount - calculated_amount) > tolerance


def parse_status(reasons):
    if (
        'EXPLICIT_AMOUNT_MISMATCH' in reasons
        or 'RATIO_SUM_EXCEEDS_100' in reasons
    ):
        return 'conflict'
    if 'AMOUNT_MISSING' in reasons:
        return 'unsupported'
    if reasons:
        return 'partial'
    return 'exact'


def status_confidence(status):
    return {'exact': 'high', 'partial': 'medium'}.get(status, 'low')


def confidence(text, ratio, amount, due_date, trigger_event):
    has_money = ratio is not None or amount is not None
    has_condition = trigger_event not in ('other', '') or bool(due_date)
    if has_money and has_condition:
        return 'high'
    if has_money:
        return 'medium'
    return 'low'


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def trim_plans(plans, contract_amount):
    """Remove false positives without silently dropping monetary conflicts."""
    cleaned = []
    for plan in plans:
        source = plan.get('source_text') or ''
        if plan.get('due_amount') is None and plan.get('ratio') is None:
            continue
        if looks_like_price_summary(source):
            continue
        cleaned.append(plan)
    return cleaned


def validate_rule_groups(rules):
    groups = {}
    for rule in rules:
        key = (
            rule.get('group_key'),
            rule.get('scope'),
            rule.get('amount_basis'),
        )
        groups.setdefault(key, []).append(rule)
    for group_rules in groups.values():
        ratios = [
            Decimal(str(rule['ratio']))
            for rule in group_rules
            if rule.get('ratio') is not None
        ]
        if len(ratios) < 2 or sum(ratios) <= Decimal('100.01'):
            continue
        for rule in group_rules:
            reasons = list(rule.get('reason_codes') or [])
            if 'RATIO_SUM_EXCEEDS_100' not in reasons:
                reasons.append('RATIO_SUM_EXCEEDS_100')
            rule['reason_codes'] = reasons
            rule['reason_codes_json'] = json.dumps(
                reasons, ensure_ascii=False
            )
            rule['parse_status'] = 'conflict'
    return rules


def propagate_group_context(rules):
    """Carry one batch/notification scope to later phases in the same clause."""
    groups = {}
    for rule in rules:
        groups.setdefault(rule.get('group_key'), []).append(rule)
    for group_rules in groups.values():
        anchor = next((
            rule
            for rule in group_rules
            if rule.get('repeat_mode') == 'each_event'
            and rule.get('scope') in {'production_notice', 'delivery_batch'}
            and rule.get('amount_basis') != 'unknown'
        ), None)
        if not anchor:
            continue
        for rule in group_rules:
            if rule is anchor or rule.get('scope') != 'contract':
                continue
            source = rule.get('source_text') or ''
            if not any(word in source for word in (
                '该批', '本批', '当批', '到货', '验收', '质保', '尾款', '余款',
            )):
                continue
            rule['scope'] = anchor['scope']
            rule['repeat_mode'] = 'each_event'
            rule['rule_type'] = 'recurring'
            if rule.get('amount_basis') in (
                'unknown',
                'contract_total_tax_inclusive',
            ):
                rule['amount_basis'] = anchor['amount_basis']
                anchor_text = (
                    anchor.get('amount_basis_text')
                    or anchor['amount_basis']
                )
                rule['amount_basis_text'] = f'沿用同组规则：{anchor_text}'
                rule['calculated_amount'] = None
            reasons = [
                code
                for code in (rule.get('reason_codes') or [])
                if code != 'AMOUNT_BASIS_INFERRED'
            ]
            rule['reason_codes'] = reasons
            rule['reason_codes_json'] = json.dumps(
                reasons, ensure_ascii=False
            )
            rule['parse_status'] = parse_status(reasons)
    return rules


def sync_plan_status(plan, rule):
    plan['parse_status'] = rule['parse_status']
    plan['reason_codes_json'] = rule['reason_codes_json']
    plan['confidence'] = status_confidence(rule['parse_status'])
    if rule['parse_status'] in ('conflict', 'unsupported'):
        plan['due_amount'] = None


def dedupe_rules(rules):
    result = []
    seen = set()
    for rule in rules:
        key = rule.get('rule_fingerprint')
        if key in seen:
            continue
        seen.add(key)
        result.append(rule)
    return result


def dedupe_plans(plans):
    result = []
    seen = set()
    for plan in plans:
        key = plan.get('rule_fingerprint') or (
            plan.get('phase_name'),
            plan.get('ratio'),
            plan.get('due_amount'),
            plan.get('due_date'),
            plan.get('source_text'),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(plan)
    return result


def block_label(block):
    if block.get('kind') == 'table_row':
        return (
            f"表格{block.get('table_index', '')}"
            f"第{block.get('row_index', '')}行"
        )
    return f"段落{block.get('index', '')}"


def fingerprint(value):
    normalized = re.sub(r'\s+', '', str(value or '')).strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def add_days(date_text, days):
    try:
        base = datetime.strptime(date_text[:10], '%Y-%m-%d')
        return (base + timedelta(days=int(days or 0))).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return ''
