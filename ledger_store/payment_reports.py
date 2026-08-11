"""Monthly payment-report query model.

The report exports every contract payment node and highlights outstanding
nodes in the selected month. Production notices are not queried or inferred.
"""

from __future__ import annotations

import calendar
import json
import re
from collections import defaultdict
from datetime import date


_LABEL_ALIASES = {
    'party_a': ('甲方', '付款单位', '采购方'),
    'bank_acceptance': ('银承', '银行承兑', '承兑期限'),
    'prior_unpaid_reason': ('上月未付原因', '上月已做计划未付款说明', '未付款原因', '延期原因'),
}


def normalize_report_month(value, *, default_next_month=True):
    text = str(value or '').strip()
    if not text and default_next_month:
        today = date.today()
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        return f'{year:04d}-{month:02d}'
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', text):
        raise ValueError('报表月份格式无效，请使用 YYYY-MM')
    return text


def _month_bounds(report_month):
    year, month = (int(part) for part in report_month.split('-'))
    end_day = calendar.monthrange(year, month)[1]
    return f'{year:04d}-{month:02d}-01', f'{year:04d}-{month:02d}-{end_day:02d}'


def _flatten_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield f'{key}：{item}'
            yield from _flatten_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_values(item)
    elif value not in (None, ''):
        yield str(value)


def _metadata_text(contract, plans):
    parts = []
    raw_values = contract.get('values_json') or ''
    if raw_values:
        try:
            parts.extend(_flatten_values(json.loads(raw_values)))
        except (TypeError, ValueError, json.JSONDecodeError):
            parts.append(str(raw_values))
    for plan in plans:
        for key in ('remark', 'condition_text', 'source_text'):
            if plan.get(key):
                parts.append(str(plan[key]))
    return '\n'.join(parts)


def _labeled_value(text, key):
    for label in _LABEL_ALIASES[key]:
        match = re.search(
            rf'(?:^|[\n；;，,。])\s*{re.escape(label)}\s*[：:]\s*([^\n；;]+)',
            text,
        )
        if match:
            return match.group(1).strip()
    if key == 'bank_acceptance' and re.search(r'银承|银行承兑', text):
        return '银承'
    return ''


def _plan_condition(plan):
    parts = []
    if plan.get('due_date'):
        parts.append(str(plan['due_date']))
    if plan.get('phase_name'):
        parts.append(str(plan['phase_name']))
    condition = plan.get('condition_text') or plan.get('trigger_event')
    if condition:
        parts.append(str(condition))
    return '，'.join(parts)


def _summarize_projects(report_rows):
    summaries = []
    by_project_subsystem = defaultdict(list)
    for row in report_rows:
        by_project_subsystem[
            (row['project_name'], row['subsystem_name'])
        ].append(row)
    for (project_name, subsystem_name), project_rows in by_project_subsystem.items():
        current_minor = sum(row['current_month_minor'] for row in project_rows)
        previous_minor = sum(row['previous_unpaid_minor'] for row in project_rows)
        summaries.append({
            'project_name': project_name,
            'subsystem_name': subsystem_name,
            'current_month_minor': current_minor,
            'previous_unpaid_minor': previous_minor,
            'planned_total_minor': current_minor + previous_minor,
            'bank_acceptance_minor': sum(
                row['bank_acceptance_minor'] for row in project_rows
            ),
            'rows': project_rows,
        })
    return summaries


def _group_report_plans(plans, month_end):
    """Normalize grouping keys and count actionable serial assignments."""
    grouped = defaultdict(list)
    unassigned_serial_count = 0
    for source_plan in plans:
        plan = dict(source_plan)
        plan['effective_subsystem_name'] = (
            str(plan.get('subsystem_name') or '').strip()
            or str(plan.get('contract_subsystem_name') or '').strip()
            or '未填写分系统'
        )
        due_minor = plan.get('due_amount_minor')
        paid_minor = plan.get('paid_amount_minor') or 0
        outstanding = max((due_minor or 0) - paid_minor, 0)
        due_date = str(plan.get('due_date') or '')
        is_relevant_unpaid = bool(
            outstanding and (not due_date or due_date <= month_end)
        )
        has_active_serial = (
            plan.get('contract_serial_id') is not None
            and plan.get('serial_status') == 'active'
        )
        if (
            not plan.get('coverage_not_applicable')
            and not has_active_serial
            and is_relevant_unpaid
        ):
            unassigned_serial_count += 1
        grouped[
            (
                plan['contract_id'],
                plan['effective_subsystem_name'],
                plan['contract_serial_id'],
            )
        ].append(plan)
    return grouped, unassigned_serial_count


def build_monthly_payment_report(get_conn, row_to_dict, report_month):
    report_month = normalize_report_month(report_month)
    month_start, month_end = _month_bounds(report_month)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.*,
                   c.contract_no, c.title AS contract_title, c.counterparty,
                   c.owner, c.project_name, c.coverage_not_applicable,
                   c.subsystem_name AS contract_subsystem_name,
                   c.values_json,
                   s.serial_no, s.amount_minor AS serial_amount_minor,
                   s.status AS serial_status
              FROM payment_plans p
              JOIN contracts c ON c.id = p.contract_id
              LEFT JOIN contract_serials s ON s.id = p.contract_serial_id
             WHERE p.confirm_status IN ('pending', 'confirmed')
               AND (c.deleted_at = '' OR c.deleted_at IS NULL)
               AND c.status != 'void'
             ORDER BY c.project_name, c.id, s.serial_no,
                      COALESCE(p.due_date, '9999-12-31'), p.id
            """
        ).fetchall()
    plans = [row_to_dict(row) for row in rows]

    diagnostics = {
        'unassigned_serial_count': 0,
        'missing_due_date_count': 0,
        'missing_due_amount_count': 0,
        'missing_serial_amount_count': 0,
    }
    grouped, diagnostics['unassigned_serial_count'] = _group_report_plans(
        plans, month_end
    )

    report_rows = []
    missing_serial_amount_ids = set()
    for (_contract_id, subsystem_name, serial_id), serial_plans in grouped.items():
        current_minor = 0
        previous_minor = 0
        current_plans = []
        previous_plans = []
        for plan in serial_plans:
            due_minor = plan.get('due_amount_minor')
            paid_minor = plan.get('paid_amount_minor') or 0
            due_date = str(plan.get('due_date') or '')
            if due_minor is None:
                if due_date and due_date <= month_end:
                    diagnostics['missing_due_amount_count'] += 1
                continue
            outstanding = max(due_minor - paid_minor, 0)
            if outstanding <= 0:
                continue
            if not due_date:
                diagnostics['missing_due_date_count'] += 1
            elif due_date < month_start:
                previous_minor += outstanding
                previous_plans.append(plan)
            elif due_date <= month_end:
                current_minor += outstanding
                current_plans.append(plan)

        planned_minor = current_minor + previous_minor
        first = serial_plans[0]
        if (
            not first.get('coverage_not_applicable')
            and first.get('serial_amount_minor') is None
        ):
            missing_serial_amount_ids.add(
                (_contract_id, subsystem_name, serial_id)
            )
        metadata = _metadata_text(first, serial_plans)
        planned_metadata = _metadata_text(
            first,
            previous_plans + current_plans,
        )
        previous_metadata = _metadata_text(first, previous_plans)
        bank_acceptance = _labeled_value(
            planned_metadata,
            'bank_acceptance',
        )
        relevant_conditions = [
            _plan_condition(plan) for plan in previous_plans + current_plans
            if _plan_condition(plan)
        ]
        nodes = []
        for plan in serial_plans:
            due_minor = plan.get('due_amount_minor')
            paid_minor = plan.get('paid_amount_minor') or 0
            due_date = str(plan.get('due_date') or '')
            nodes.append({
                'amount_minor': due_minor,
                'condition': _plan_condition(plan),
                'is_paid': bool(
                    plan.get('payment_status') == 'paid' or
                    (due_minor is not None and paid_minor >= due_minor)
                ),
                'is_current': bool(
                    due_date and month_start <= due_date <= month_end and
                    due_minor is not None and due_minor > paid_minor
                ),
            })
        report_rows.append({
            'project_name': first.get('project_name') or '未归类项目',
            'subsystem_name': subsystem_name,
            'contract_serial_id': serial_id,
            'serial_no': first.get('serial_no'),
            'serial_amount_minor': first.get('serial_amount_minor'),
            'coverage_not_applicable': bool(
                first.get('coverage_not_applicable')
            ),
            'contract_no': first.get('contract_no') or '',
            'contract_title': first.get('contract_title') or '',
            'party_a': _labeled_value(metadata, 'party_a'),
            'party_b': first.get('counterparty') or '',
            'nodes': nodes,
            'current_month_minor': current_minor,
            'previous_unpaid_minor': previous_minor,
            'planned_payment_minor': planned_minor,
            'payment_condition': '\n'.join(dict.fromkeys(relevant_conditions)),
            'overdue_text': (
                f"是，最早应付 {min(plan['due_date'] for plan in previous_plans)}"
                if previous_plans else '否'
            ),
            'bank_acceptance': bank_acceptance,
            'bank_acceptance_minor': planned_minor if bank_acceptance else 0,
            'prior_unpaid_reason': (
                _labeled_value(previous_metadata, 'prior_unpaid_reason')
                if previous_minor else ''
            ),
        })

    diagnostics['missing_serial_amount_count'] = len(missing_serial_amount_ids)
    report_rows.sort(
        key=lambda row: (
            row['project_name'],
            row['subsystem_name'],
            row['contract_no'],
            row['serial_no'] if row['serial_no'] is not None else 10**18,
        )
    )
    return {
        'report_month': report_month,
        'month_start': month_start,
        'month_end': month_end,
        'rows': report_rows,
        'projects': _summarize_projects(report_rows),
        'node_count': max((len(row['nodes']) for row in report_rows), default=1),
        'diagnostics': diagnostics,
    }
