"""Shared parsing for editable payment-plan form rows."""

from __future__ import annotations

import json

from utils import field_utils
from utils.generation_utils import has_payment_content
from utils.security import (
    MAX_PLAN_ROWS,
    MAX_TEXT_VALUE_LENGTH,
    limit_text,
)


def payment_filter_args(form_or_args):
    return {
        'view': str(form_or_args.get('view', 'work') or 'work').strip(),
        'confirm_status': str(
            form_or_args.get('confirm_status', '') or ''
        ).strip(),
        'payment_status': str(
            form_or_args.get('payment_status', '') or ''
        ).strip(),
        'start_date': str(
            form_or_args.get('start_date', '') or ''
        ).strip(),
        'end_date': str(form_or_args.get('end_date', '') or '').strip(),
        'project_name': str(
            form_or_args.get('project_name', '') or ''
        ).strip(),
    }


def parse_plan_ids(raw):
    try:
        ids = [int(item) for item in json.loads(raw or '[]')]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('付款计划 ID 列表无效') from exc
    unique_ids = list(dict.fromkeys(ids))
    if len(unique_ids) > MAX_PLAN_ROWS:
        raise ValueError(f'单次不能超过 {MAX_PLAN_ROWS} 条付款计划')
    return unique_ids


def normalized_form_date(form, name, default=''):
    raw = str(form.get(name, '') or '').strip() or default
    normalized = field_utils.normalize_date(raw)
    if not normalized:
        raise ValueError('日期格式无效，请使用 YYYY-MM-DD')
    return normalized


def contract_serial_entries(form, max_rows):
    try:
        count = int(form.get('serial_count', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('合同内编号数量无效') from exc
    if count < 0 or count > max_rows:
        raise ValueError(f'合同内编号数量不能超过 {max_rows}')
    return [
        {
            'id': form.get(f'serial_{idx}_id', ''),
            'amount': form.get(f'serial_{idx}_amount', ''),
            'remark': form.get(f'serial_{idx}_remark', ''),
        }
        for idx in range(count)
    ]


def payment_rule_values(form):
    def optional_number(name, label):
        raw = str(form.get(name, '') or '').strip()
        if not raw:
            return None
        value = field_utils.float_or_none(raw)
        if value is None:
            raise ValueError(f'{label}必须是有效数字')
        return value

    days_raw = str(form.get('trigger_days', '') or '').strip()
    try:
        trigger_days = int(days_raw) if days_raw else None
    except (TypeError, ValueError) as exc:
        raise ValueError('后置天数必须是整数') from exc
    if trigger_days is not None and not 0 <= trigger_days <= 36_500:
        raise ValueError('后置天数必须在0到36500之间')
    return {
        'phase_name': str(form.get('phase_name', '') or '').strip()[:120],
        'scope': str(form.get('scope', 'contract') or 'contract'),
        'trigger_event_type': str(
            form.get('trigger_event_type', 'other') or 'other'
        )[:80],
        'trigger_event': str(
            form.get('trigger_event', '') or ''
        ).strip()[:200],
        'trigger_days': trigger_days,
        'amount_basis': str(
            form.get('amount_basis', 'unknown') or 'unknown'
        )[:80],
        'amount_basis_text': str(
            form.get('amount_basis_text', '') or ''
        ).strip()[:300],
        'ratio': optional_number('ratio', '付款比例'),
        'explicit_amount': optional_number(
            'explicit_amount', '合同明确金额'
        ),
        'calculated_amount': optional_number(
            'calculated_amount', '比例计算金额'
        ),
        'repeat_mode': str(
            form.get('repeat_mode', 'once') or 'once'
        ),
    }


def payment_rule_event(form):
    event_date = str(form.get('event_date', '') or '').strip()
    normalized_event_date = (
        field_utils.normalize_date(event_date) if event_date else ''
    )
    if event_date and not normalized_event_date:
        raise ValueError('业务事件日期格式无效，请使用 YYYY-MM-DD')
    return {
        'reference_no': str(
            form.get('reference_no', '') or ''
        ).strip(),
        'event_date': normalized_event_date,
        'reference_name': str(
            form.get('reference_name', '') or ''
        ).strip(),
        'base_amount': field_utils.float_or_none(
            str(form.get('base_amount', '') or '').strip()
        ),
    }


def payment_plan_changes(form):
    try:
        count = int(form.get('plan_count', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('付款计划行数无效') from exc
    if count < 0 or count > MAX_PLAN_ROWS:
        raise ValueError(
            f'付款计划行数必须在 0 到 {MAX_PLAN_ROWS} 之间'
        )

    changes = []
    for idx in range(count):
        delete_flag = form.get(f'plan_{idx}_delete') == '1'
        plan_id = str(form.get(f'plan_{idx}_id', '') or '').strip()
        if delete_flag:
            if plan_id:
                try:
                    changes.append({'id': int(plan_id), 'delete': True})
                except ValueError as exc:
                    raise ValueError('付款计划 ID 无效') from exc
            continue

        row = payment_row_from_form(idx, form)
        plan_id = row.pop('id', '')
        if plan_id:
            try:
                parsed_id = int(plan_id)
            except ValueError as exc:
                raise ValueError('付款计划 ID 或状态无效') from exc
            changes.append({'id': parsed_id, 'data': row})
        elif has_payment_content(row):
            row['confirm_status'] = (
                row.get('confirm_status') or 'confirmed'
            )
            changes.append({'data': row})
    return changes


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
