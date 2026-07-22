"""Safe navigation helpers for the contract detail workspace."""

import re

from flask import url_for


CONTRACT_TABS = ('overview', 'payments', 'production', 'invoices', 'history')
_ANCHOR_RE = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


def normalize_contract_tab(value, default='overview'):
    value = str(value or '').strip()
    return value if value in CONTRACT_TABS else default


def contract_detail_location(
    contract_id, form_or_args=None, *, default_tab='overview', error=''
):
    source = form_or_args or {}
    tab = normalize_contract_tab(source.get('return_tab'), default_tab)
    params = {'tab': tab}
    page_name = {
        'payments': 'plan_page',
        'production': 'notice_page',
        'invoices': 'invoice_page',
        'history': 'history_page',
    }.get(tab)
    if page_name:
        raw_page = str(source.get('return_page', '') or '').strip()
        try:
            page = max(1, int(raw_page)) if raw_page else 1
        except ValueError:
            page = 1
        if page > 1:
            params[page_name] = page
    if error:
        params['error'] = str(error)[:500]
    location = url_for('contract_detail', contract_id=contract_id, **params)
    anchor = str(source.get('return_anchor', '') or '').strip()
    if anchor and _ANCHOR_RE.fullmatch(anchor):
        location += f'#{anchor}'
    return location
