"""Parsing support shared by contract ledger routes."""

from __future__ import annotations

from utils.field_utils import float_or_none, normalize_date
from utils.generation_utils import parse_contract_classification
from utils.security import MAX_COUNTERPARTY_LENGTH, limit_text


def parse_contract_update(form, status):
    classification = parse_contract_classification(form)
    amount_raw = str(form.get('amount', '') or '').strip()
    amount = float_or_none(amount_raw)
    if amount_raw and amount is None:
        raise ValueError('合同金额必须是有效数字')
    sign_date_raw = str(form.get('sign_date', '') or '').strip()
    expiry_date_raw = str(form.get('expiry_date', '') or '').strip()
    sign_date = normalize_date(sign_date_raw) if sign_date_raw else ''
    expiry_date = normalize_date(expiry_date_raw) if expiry_date_raw else ''
    if sign_date_raw and not sign_date:
        raise ValueError('签订日期格式无效，请使用 YYYY-MM-DD')
    if expiry_date_raw and not expiry_date:
        raise ValueError('到期日期格式无效，请使用 YYYY-MM-DD')
    return {
        'contract_no': limit_text(form.get('contract_no', '').strip(), 80),
        'title': limit_text(form.get('title', '').strip(), 200) or '未命名合同',
        'counterparty': limit_text(
            form.get('counterparty', '').strip(), MAX_COUNTERPARTY_LENGTH
        ),
        'amount': amount,
        'sign_date': sign_date,
        'expiry_date': expiry_date,
        'owner': limit_text(form.get('owner', '').strip(), 60),
        'status': status,
        **classification,
    }
