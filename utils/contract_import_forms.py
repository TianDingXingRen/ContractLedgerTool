"""Framework-neutral parsing for reviewed contract imports."""

from __future__ import annotations

import json

from utils.constants import ContractStatus
from utils.field_utils import float_or_none, normalize_date
from utils.generation_utils import (
    has_payment_content,
    parse_contract_classification,
)
from utils.payment_forms import payment_row_from_form
from utils.security import (
    MAX_COUNTERPARTY_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
    limit_text,
)


MAX_IMPORTED_PLANS = 30
MAX_IMPORTED_RULES = 60
CONTRACT_STATUSES = {status.value for status in ContractStatus}


def _normalized_date(form, name, label):
    raw = str(form.get(name, '') or '').strip()
    if not raw:
        return ''
    value = normalize_date(raw)
    if not value:
        raise ValueError(f'{label}格式无效，请使用 YYYY-MM-DD')
    return value


def summary_from_form(form):
    title = limit_text(
        str(form.get('title', '') or '').strip(), 200
    )
    if not title:
        raise ValueError('合同名称不能为空')
    amount_raw = str(form.get('amount', '') or '').strip()
    amount = float_or_none(amount_raw)
    if amount_raw and amount is None:
        raise ValueError('合同金额必须是有效数字')
    if amount is not None and amount < 0:
        raise ValueError('合同金额不能为负数')
    status = str(form.get('status', 'draft') or 'draft').strip()
    if status not in CONTRACT_STATUSES:
        raise ValueError('合同状态无效')
    classification = parse_contract_classification(form)
    return {
        'contract_no': limit_text(
            str(form.get('contract_no', '') or '').strip(), 80
        ),
        'title': title,
        'counterparty': limit_text(
            str(form.get('counterparty', '') or '').strip(),
            MAX_COUNTERPARTY_LENGTH,
        ),
        'amount': amount,
        'sign_date': _normalized_date(
            form, 'sign_date', '签订日期'
        ),
        'expiry_date': _normalized_date(
            form, 'expiry_date', '到期日期'
        ),
        'owner': limit_text(
            str(form.get('owner', '') or '').strip(), 60
        ),
        'status': status,
        'project_name': limit_text(
            classification.get('project_name') or '',
            MAX_PROJECT_NAME_LENGTH,
        ),
        'coverage_start': classification.get('coverage_start'),
        'coverage_end': classification.get('coverage_end'),
    }


def summary_for_render(form):
    keys = (
        'contract_no',
        'title',
        'counterparty',
        'amount',
        'sign_date',
        'expiry_date',
        'owner',
        'status',
        'project_name',
        'coverage_start',
        'coverage_end',
    )
    return {
        key: str(form.get(key, '') or '').strip() for key in keys
    }


def plans_for_render(form):
    try:
        count = min(
            max(int(form.get('plan_count', 0)), 0),
            MAX_IMPORTED_PLANS,
        )
    except (TypeError, ValueError):
        return []
    keys = (
        'phase_name',
        'payment_type',
        'trigger_event',
        'trigger_days',
        'expected_trigger_date',
        'due_date',
        'ratio',
        'due_amount',
        'condition_text',
        'source_text',
        'confidence',
        'remark',
    )
    rows = []
    for index in range(count):
        prefix = f'plan_{index}_'
        row = {
            key: str(form.get(prefix + key, '') or '').strip()
            for key in keys
        }
        row['_include'] = (
            str(form.get(prefix + 'include', '') or '') == '1'
        )
        rows.append(row)
    return rows


def plans_from_form(form):
    try:
        count = int(form.get('plan_count', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('付款计划行数无效') from exc
    if count < 0 or count > MAX_IMPORTED_PLANS:
        raise ValueError(
            f'导入时付款计划不能超过 {MAX_IMPORTED_PLANS} 条'
        )
    plans = []
    for index in range(count):
        if str(
            form.get(f'plan_{index}_include', '') or ''
        ) != '1':
            continue
        row = payment_row_from_form(index, form)
        row.pop('id', None)
        row['confirm_status'] = 'pending'
        row['payment_status'] = 'unpaid'
        row['paid_amount'] = 0
        row['paid_date'] = ''
        if has_payment_content(row):
            plans.append(row)
    return plans


def rules_for_render(form):
    try:
        count = min(
            max(int(form.get('rule_count', 0)), 0),
            MAX_IMPORTED_RULES,
        )
    except (TypeError, ValueError):
        return []
    keys = (
        'group_key',
        'phase_name',
        'rule_type',
        'scope',
        'trigger_event_type',
        'trigger_event',
        'trigger_days',
        'due_date',
        'conditions_json',
        'condition_logic',
        'amount_basis',
        'amount_basis_text',
        'ratio',
        'explicit_amount',
        'calculated_amount',
        'repeat_mode',
        'source_text',
        'source_block',
        'rule_fingerprint',
        'source_fingerprint',
        'extractor_version',
        'rule_version',
        'parse_status',
        'reason_codes_json',
        'confirm_status',
    )
    rows = []
    for index in range(count):
        prefix = f'rule_{index}_'
        row = {
            key: str(form.get(prefix + key, '') or '').strip()
            for key in keys
        }
        row['_include'] = (
            str(form.get(prefix + 'include', '') or '') == '1'
        )
        rows.append(row)
    return rows


def _json_list(value, label):
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f'{label}格式无效') from exc
    return value


def _optional_rule_number(form, prefix, name, label):
    raw = str(form.get(prefix + name, '') or '').strip()
    if not raw:
        return None
    value = float_or_none(raw)
    if value is None:
        raise ValueError(f'{label}必须是有效数字')
    return value


def _rule_from_form(form, index):
    prefix = f'rule_{index}_'
    ratio = _optional_rule_number(
        form, prefix, 'ratio', '付款规则比例'
    )
    if ratio is not None and not 0 <= ratio <= 100:
        raise ValueError('付款规则比例必须在0到100之间')
    trigger_days_raw = str(
        form.get(prefix + 'trigger_days', '') or ''
    ).strip()
    try:
        trigger_days = (
            int(trigger_days_raw) if trigger_days_raw else None
        )
    except ValueError as exc:
        raise ValueError('付款规则后置天数必须是整数') from exc
    conditions_json = _json_list(
        str(form.get(prefix + 'conditions_json', '[]') or '[]'),
        '付款条件',
    )
    reason_codes_json = _json_list(
        str(
            form.get(prefix + 'reason_codes_json', '[]') or '[]'
        ),
        '付款规则原因码',
    )
    try:
        rule_version = int(
            str(form.get(prefix + 'rule_version', '1') or '1')
        )
    except ValueError as exc:
        raise ValueError('付款规则版本无效') from exc
    return {
        'group_key': limit_text(
            str(form.get(prefix + 'group_key', '') or ''), 128
        ),
        'phase_name': limit_text(
            str(form.get(prefix + 'phase_name', '') or ''), 120
        ),
        'rule_type': str(
            form.get(prefix + 'rule_type', 'conditional')
            or 'conditional'
        ),
        'scope': str(
            form.get(prefix + 'scope', 'contract') or 'contract'
        ),
        'trigger_event_type': limit_text(
            str(
                form.get(prefix + 'trigger_event_type', 'other')
                or 'other'
            ),
            80,
        ),
        'trigger_event': limit_text(
            str(form.get(prefix + 'trigger_event', '') or ''), 200
        ),
        'trigger_days': trigger_days,
        'due_date': str(
            form.get(prefix + 'due_date', '') or ''
        ).strip(),
        'conditions_json': conditions_json,
        'condition_logic': str(
            form.get(prefix + 'condition_logic', 'SINGLE')
            or 'SINGLE'
        ),
        'amount_basis': limit_text(
            str(
                form.get(prefix + 'amount_basis', 'unknown')
                or 'unknown'
            ),
            80,
        ),
        'amount_basis_text': limit_text(
            str(form.get(prefix + 'amount_basis_text', '') or ''),
            300,
        ),
        'ratio': ratio,
        'explicit_amount': _optional_rule_number(
            form, prefix, 'explicit_amount', '合同明确金额'
        ),
        'calculated_amount': _optional_rule_number(
            form, prefix, 'calculated_amount', '比例计算金额'
        ),
        'repeat_mode': str(
            form.get(prefix + 'repeat_mode', 'once') or 'once'
        ),
        'source_text': limit_text(
            str(form.get(prefix + 'source_text', '') or ''), 10_000
        ),
        'source_block': limit_text(
            str(form.get(prefix + 'source_block', '') or ''), 120
        ),
        'rule_fingerprint': limit_text(
            str(
                form.get(prefix + 'rule_fingerprint', '') or ''
            ),
            128,
        ),
        'source_fingerprint': limit_text(
            str(
                form.get(prefix + 'source_fingerprint', '') or ''
            ),
            128,
        ),
        'extractor_version': limit_text(
            str(
                form.get(prefix + 'extractor_version', '') or ''
            ),
            80,
        ),
        'rule_version': rule_version,
        'parse_status': str(
            form.get(prefix + 'parse_status', 'manual') or 'manual'
        ),
        'reason_codes_json': reason_codes_json,
        'confirm_status': 'pending',
        'user_modified': 0,
    }


def rules_from_form(form):
    try:
        count = int(form.get('rule_count', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('付款规则行数无效') from exc
    if count < 0 or count > MAX_IMPORTED_RULES:
        raise ValueError(
            f'导入时付款规则不能超过 {MAX_IMPORTED_RULES} 条'
        )
    rules = []
    for index in range(count):
        prefix = f'rule_{index}_'
        if str(form.get(prefix + 'include', '') or '') != '1':
            continue
        rule = _rule_from_form(form, index)
        if rule['source_text'] or rule['phase_name']:
            rules.append(rule)
    return rules
