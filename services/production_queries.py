"""Read models and business preconditions for production notice pages."""

from __future__ import annotations

from datetime import date

import ledger_store
from core.domain_errors import NotFoundError


PRODUCTION_NOTICE_STATUSES = {
    '',
    'draft',
    'issued',
    'acknowledged',
    'closed',
    'cancelled',
}


class MissingContractItemsError(ValueError):
    """The contract has no product baseline for a production notice."""


class ProductionNoticeLockedError(ValueError):
    """A non-draft production notice cannot be edited."""


def contract_item_page(contract_id):
    contract = ledger_store.get_contract(contract_id)
    if not contract:
        raise NotFoundError('合同记录不存在')
    return {
        'contract': contract,
        'items': ledger_store.list_contract_items(contract_id),
        'item_history': ledger_store.list_contract_item_history(
            contract_id
        ),
    }


def production_notice_page(status='', contract_id=None, page=1):
    safe_status = (
        status if status in PRODUCTION_NOTICE_STATUSES else ''
    )
    result = ledger_store.list_production_notices(
        contract_id=contract_id, status=safe_status, page=page
    )
    return {
        'notices': result['rows'],
        'status': safe_status,
        'contract_id': contract_id,
        'page': result['page'],
        'pages': result['pages'],
        'total': result['total'],
        'summary': ledger_store.summarize_production_notices(
            contract_id=contract_id, status=safe_status
        ),
        'contract': ledger_store.get_contract(contract_id) if contract_id else None,
    }


def production_notice_detail(notice_id):
    notice = ledger_store.get_production_notice(notice_id)
    if not notice:
        raise NotFoundError('投产通知不存在')
    return notice


def new_production_notice_context(contract_id, error=''):
    contract = ledger_store.get_contract(contract_id)
    if not contract:
        raise NotFoundError('合同记录不存在')
    if not ledger_store.list_contract_items(contract_id):
        raise MissingContractItemsError(
            '请先维护合同产品基线，再创建投产通知'
        )
    return _notice_form_context(contract, error=error)


def editable_production_notice_context(notice_id, error=''):
    notice = production_notice_detail(notice_id)
    if notice['status'] != 'draft':
        raise ProductionNoticeLockedError(
            '正式发出后的投产通知已锁定，不能直接修改'
        )
    contract = ledger_store.get_contract(notice['contract_id'])
    return _notice_form_context(contract, notice, error)


def _notice_form_context(contract, notice=None, error=''):
    contract_items = ledger_store.list_contract_items(contract['id'])
    values = {}
    if notice:
        values = {
            item['contract_item_id']: item
            for item in notice.get('items', [])
        }
    return {
        'contract': contract,
        'notice': notice,
        'contract_items': contract_items,
        'notice_item_values': values,
        'today': date.today().strftime('%Y-%m-%d'),
        'error': error,
    }
