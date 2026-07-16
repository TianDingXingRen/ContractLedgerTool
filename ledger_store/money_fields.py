"""Canonical money-field conversion for ledger records.

SQLite stores authoritative monetary values as integer minor units.  The
legacy REAL columns remain compatibility mirrors for templates and callers
that expect amounts in yuan.  Keeping those conversion rules here prevents
individual repositories from drifting apart.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableSequence
from typing import Any

from utils.money import to_minor


PUBLIC_MINOR_FIELDS = (
    ('amount', 'amount_minor'),
    ('due_amount', 'due_amount_minor'),
    ('paid_amount', 'paid_amount_minor'),
    ('contract_amount', 'contract_amount_minor'),
)


def amount_pair(value, *, allow_none=True):
    """Return one amount as ``(integer minor units, compatibility float)``."""
    minor = to_minor(value, allow_none=allow_none)
    return minor, (None if minor is None else float(minor) / 100)


def with_public_amounts(row):
    """Copy a DB row and expose authoritative minor fields as yuan values."""
    if row is None:
        return None
    result = dict(row)
    for public_key, minor_key in PUBLIC_MINOR_FIELDS:
        if minor_key in result and result[minor_key] is not None:
            result[public_key] = float(result[minor_key]) / 100
    return result


def normalize_payment_consistency(plan: Mapping[str, Any]):
    """Normalize money mirrors and derive payment state from integer amounts."""
    row = dict(plan)
    due_minor, due_amount = amount_pair(row.get('due_amount'))
    paid_minor, paid_amount = amount_pair(
        row.get('paid_amount') or 0, allow_none=False
    )
    row['due_amount'] = due_amount
    row['due_amount_minor'] = due_minor
    row['paid_amount'] = paid_amount
    row['paid_amount_minor'] = paid_minor
    if due_minor is not None and paid_minor > due_minor:
        raise ValueError('已付金额不能大于应付金额')
    if paid_minor > 0 and not str(row.get('paid_date') or '').strip():
        raise ValueError('填写已付金额后必须填写实付日期')

    if paid_minor <= 0:
        row['payment_status'] = 'unpaid'
        row['paid_date'] = ''
    elif due_minor is not None and paid_minor >= due_minor:
        row['payment_status'] = 'paid'
    else:
        row['payment_status'] = 'partial'
    return row


def append_plan_assignment(
    assignments: MutableSequence[str],
    values: MutableSequence[Any],
    key: str,
    row: Mapping[str, Any],
):
    """Append one plan update while keeping REAL and minor columns in sync."""
    if key == 'due_amount':
        assignments.extend(['due_amount = ?', 'due_amount_minor = ?'])
        values.extend([row.get('due_amount'), row.get('due_amount_minor')])
        return
    if key == 'paid_amount':
        assignments.extend(['paid_amount = ?', 'paid_amount_minor = ?'])
        values.extend([row.get('paid_amount') or 0, row.get('paid_amount_minor') or 0])
        return
    assignments.append(f'{key} = ?')
    values.append(row[key])
