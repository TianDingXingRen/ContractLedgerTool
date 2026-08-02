"""Multi-round negotiation records and price movement analysis."""

from __future__ import annotations

from decimal import Decimal

import procurement_store
from utils.money import to_minor


def _money_to_minor(value):
    raw = str(value or '').replace(',', '').strip()
    if not raw:
        return None
    try:
        return to_minor(raw, allow_none=False)
    except ValueError as exc:
        raise ValueError(f'谈判金额无效：{exc}') from exc


def negotiation_view(project_id, editing_round_no=None):
    project = procurement_store.get_project(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    quotes = procurement_store.list_quotes(project_id)
    rounds = procurement_store.list_negotiation_rounds(project_id)
    editing_round = None
    if editing_round_no:
        editing_round = next(
            (row for row in rounds if int(row['round_no']) == int(editing_round_no)),
            None,
        )
        if not editing_round:
            raise ValueError('谈判轮次不存在')
        editing_commitments = {
            item['supplier_id']: item for item in editing_round.get('commitments') or []
        }
    else:
        editing_commitments = {}
    grouped = {}
    for quote in quotes:
        grouped.setdefault(quote['supplier_id'], []).append(quote)
    suppliers = []
    for supplier in procurement_store.list_project_suppliers(project_id):
        supplier_id = supplier['id']
        rows = grouped.get(supplier_id, [])
        rows.sort(key=lambda item: item['quote_round'])
        first = rows[0] if rows else None
        latest = rows[-1] if rows else None
        reduction = (first['total_amount_minor'] - latest['total_amount_minor']) if first and latest else 0
        percent = (Decimal(reduction) / Decimal(first['total_amount_minor']) * 100
                   if first and first['total_amount_minor'] else Decimal('0'))
        suppliers.append({
            'supplier_id': supplier_id, 'supplier_name': supplier['supplier_name'],
            'quotes': rows, 'first_amount_minor': first['total_amount_minor'] if first else None,
            'latest_amount_minor': latest['total_amount_minor'] if latest else None,
            'reduction_minor': reduction,
            'reduction_percent': f'{percent:.2f}', 'latest_quote': latest,
            'editing_commitment': editing_commitments.get(supplier_id, {}),
        })
    next_round_no = (max((int(row['round_no']) for row in rounds), default=0) + 1)
    return {
        'project': project, 'suppliers': suppliers,
        'rounds': rounds,
        'editing_round': editing_round,
        'next_round_no': next_round_no,
    }


def save_round(project_id, form):
    try:
        round_no = int(form.get('round_no') or 0)
    except ValueError as exc:
        raise ValueError('谈判轮次必须为整数') from exc
    if round_no < 1:
        raise ValueError('谈判轮次必须大于等于 1')
    suppliers = procurement_store.list_project_suppliers(project_id)
    latest = {row['supplier_id']: row for row in procurement_store.get_latest_quotes(project_id)}
    commitments = []
    for supplier in suppliers:
        supplier_id = supplier['id']
        quote = latest.get(supplier_id)
        manual_amount_minor = _money_to_minor(form.get(f'amount_{supplier_id}'))
        commitment = str(form.get(f'commitment_{supplier_id}') or '').strip()
        delivery = str(form.get(f'delivery_{supplier_id}') or (quote or {}).get('delivery_period') or '').strip()
        payment = str(form.get(f'payment_{supplier_id}') or (quote or {}).get('payment_terms') or '').strip()
        if not quote and manual_amount_minor is None and not any((commitment, delivery, payment)):
            continue
        commitments.append({
            'supplier_id': supplier_id, 'quote_id': quote['id'] if quote else None,
            'quote_amount_minor': manual_amount_minor if manual_amount_minor is not None else (
                quote['total_amount_minor'] if quote else None
            ),
            'delivery_period': delivery, 'payment_terms': payment, 'commitment': commitment,
        })
    return procurement_store.save_negotiation_round(
        project_id, round_no, str(form.get('meeting_date') or ''),
        str(form.get('summary') or '').strip(), commitments,
    )
