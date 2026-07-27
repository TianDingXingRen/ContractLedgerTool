"""Shared parsing for editable payment-plan form rows."""

from __future__ import annotations

from utils import field_utils
from utils.security import MAX_TEXT_VALUE_LENGTH, limit_text


def payment_row_from_form(idx, form):
    prefix = f'plan_{idx}_'

    def optional_number(name, label, default=None):
        raw = str(form.get(prefix + name, '') or '').strip()
        if not raw:
            return default
        parsed = field_utils.float_or_none(raw)
        if parsed is None:
            raise ValueError(f'{label}必须是有效数字')
        return parsed

    paid_amount = optional_number('paid_amount', '已付金额', 0)
    ratio = optional_number('ratio', '付款比例')
    if ratio is not None and (ratio < 0 or ratio > 100):
        raise ValueError('付款比例必须在 0 到 100 之间')
    due_amount = optional_number('due_amount', '应付金额')
    explicit_amount = optional_number('explicit_amount', '合同明确金额')
    calculated_amount = optional_number('calculated_amount', '比例计算金额')
    if paid_amount < 0 or (due_amount is not None and due_amount < 0):
        raise ValueError('付款金额不能为负数')

    def optional_date(name, label):
        raw = str(form.get(prefix + name, '') or '').strip()
        if not raw:
            return ''
        normalized = field_utils.normalize_date(raw)
        if not normalized:
            raise ValueError(f'{label}格式无效，请使用 YYYY-MM-DD')
        return normalized

    trigger_days_raw = str(form.get(prefix + 'trigger_days', '') or '').strip()
    try:
        trigger_days = int(trigger_days_raw) if trigger_days_raw else None
    except (TypeError, ValueError) as exc:
        raise ValueError('后置天数必须是整数') from exc
    if trigger_days is not None and not 0 <= trigger_days <= 36_500:
        raise ValueError('后置天数必须在 0 到 36500 之间')
    contract_serial_raw = str(
        form.get(prefix + 'contract_serial_id', '') or ''
    ).strip()
    try:
        contract_serial_id = int(contract_serial_raw) if contract_serial_raw else None
    except (TypeError, ValueError) as exc:
        raise ValueError('合同内编号无效') from exc
    return {
        'id': str(form.get(prefix + 'id', '') or '').strip(),
        'contract_serial_id': contract_serial_id,
        'phase_name': limit_text(str(form.get(prefix + 'phase_name', '') or '').strip(), 120),
        'payment_type': str(form.get(prefix + 'payment_type', 'conditional') or 'conditional').strip(),
        'trigger_event': limit_text(str(form.get(prefix + 'trigger_event', '') or '').strip(), 200),
        'trigger_days': trigger_days,
        'expected_trigger_date': optional_date('expected_trigger_date', '预计触发日期'),
        'due_date': optional_date('due_date', '应付日期'),
        'ratio': ratio,
        'due_amount': due_amount,
        'amount_basis': limit_text(
            str(form.get(prefix + 'amount_basis', '') or '').strip(), 80
        ),
        'explicit_amount': explicit_amount,
        'calculated_amount': calculated_amount,
        'parse_status': str(
            form.get(prefix + 'parse_status', 'manual') or 'manual'
        ).strip(),
        'reason_codes_json': limit_text(
            str(form.get(prefix + 'reason_codes_json', '[]') or '[]').strip(), 2000
        ),
        'rule_fingerprint': limit_text(
            str(form.get(prefix + 'rule_fingerprint', '') or '').strip(), 128
        ),
        'extractor_version': limit_text(
            str(form.get(prefix + 'extractor_version', '') or '').strip(), 80
        ),
        'paid_amount': paid_amount,
        'paid_date': optional_date('paid_date', '实付日期'),
        'condition_text': limit_text(
            str(form.get(prefix + 'condition_text', '') or '').strip(),
            MAX_TEXT_VALUE_LENGTH,
        ),
        'source_text': limit_text(
            str(form.get(prefix + 'source_text', '') or '').strip(),
            MAX_TEXT_VALUE_LENGTH,
        ),
        'confidence': str(form.get(prefix + 'confidence', 'low') or 'low').strip(),
        'confirm_status': str(form.get(prefix + 'confirm_status', 'pending') or 'pending').strip(),
        'payment_status': str(form.get(prefix + 'payment_status', 'unpaid') or 'unpaid').strip(),
        'remark': limit_text(str(form.get(prefix + 'remark', '') or '').strip(), 500),
    }
