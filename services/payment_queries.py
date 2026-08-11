"""Read models used by payment HTTP and API adapters."""

from __future__ import annotations

from datetime import timedelta

import ledger_store
from ledger_store import list_queries
from utils.generation_utils import next_month_range


PAYMENT_STATUSES = {'work', 'detail'}


def due_soon_payload(days):
    safe_days = max(0, min(days or 7, 365))
    payments = ledger_store.get_due_soon_payments(days=safe_days)
    total = sum(
        (payment.get('due_amount') or 0)
        - (payment.get('paid_amount') or 0)
        for payment in payments
    )
    return {
        'count': len(payments),
        'total_amount': round(total, 2),
        'payments': [
            {
                'id': payment['id'],
                'contract_id': payment['contract_id'],
                'contract_no': payment.get('contract_no', ''),
                'contract_title': payment.get('contract_title', ''),
                'phase_name': payment.get('phase_name', ''),
                'due_date': payment.get('due_date', ''),
                'due_amount': payment.get('due_amount', 0),
                'paid_amount': payment.get('paid_amount', 0),
                'counterparty': payment.get('counterparty', ''),
                'owner': payment.get('owner', ''),
                'project_name': payment.get('project_name', ''),
                'coverage_start': payment.get('coverage_start'),
                'coverage_end': payment.get('coverage_end'),
                'coverage_not_applicable': bool(
                    payment.get('coverage_not_applicable')
                ),
            }
            for payment in payments
        ],
    }


def payment_plan_page(filters, page, today):
    view_mode = filters.get('view', 'work')
    if view_mode not in PAYMENT_STATUSES:
        view_mode = 'work'

    query = {
        key: filters.get(key, '')
        for key in (
            'contract_id',
            'confirm_status',
            'payment_status',
            'start_date',
            'end_date',
            'project_name',
        )
    }
    result = ledger_store.list_payment_plans(page=page, **query)
    today_str = today.strftime('%Y-%m-%d')
    overdue_end = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    due_soon_end = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    for row in result['rows']:
        outstanding = max(
            (row.get('due_amount') or 0) - (row.get('paid_amount') or 0),
            0,
        )
        due_date = row.get('due_date') or ''
        is_void = row.get('confirm_status') == 'void'
        is_unpaid = row.get('payment_status') != 'paid' and not is_void
        row['unpaid_amount'] = outstanding if is_unpaid else 0
        row['can_bulk_select'] = not is_void
        row['is_overdue'] = bool(
            due_date and due_date < today_str and is_unpaid
        )
        row['is_due_soon'] = bool(
            due_date
            and today_str < due_date <= due_soon_end
            and is_unpaid
        )

    next_start, next_end = next_month_range()
    return {
        'plans': result['rows'],
        'selectable_plan_ids': [
            row['id'] for row in result['rows'] if row['can_bulk_select']
        ],
        **query,
        'payment_contract_options': (
            list_queries.list_payment_plan_contract_options(
                ledger_store.get_conn,
                ledger_store.row_to_dict,
            )
        ),
        'project_names': ledger_store.list_project_names(),
        'page': result['page'],
        'pages': result['pages'],
        'total': result['total'],
        'next_start': next_start,
        'next_end': next_end,
        'today': today,
        'overdue_end': overdue_end,
        'due_soon_end': due_soon_end,
        'view_mode': view_mode,
        'payment_summary': ledger_store.summarize_payment_plans(
            **query, today=today
        ),
        'default_report_month': next_start[:7],
    }
