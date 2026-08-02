"""Application commands for contract items and production notices."""

from __future__ import annotations

import sqlite3

import ledger_store
from core.domain_errors import NotFoundError


NOTICE_ACTION_MESSAGES = {
    'issue': '投产通知已正式发出并锁定',
    'acknowledge': '已登记供应商收悉',
    'close': '投产通知已关闭',
    'cancel': '投产通知已取消',
}


def _require_contract(contract_id):
    contract = ledger_store.get_contract(contract_id)
    if not contract:
        raise NotFoundError('合同记录不存在')
    return contract


def _require_notice(notice_id):
    notice = ledger_store.get_production_notice(notice_id)
    if not notice:
        raise NotFoundError('投产通知不存在')
    return notice


def save_contract_items(contract_id, rows, operator=''):
    _require_contract(contract_id)
    try:
        return ledger_store.save_contract_items(
            contract_id, rows, operator=operator
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError('合同产品行号重复') from exc


def sync_contract_items_from_procurement(contract_id):
    _require_contract(contract_id)
    report = ledger_store.sync_contract_items_from_procurement(contract_id)
    detail = f"新增 {report['created']} 条，更新 {report['updated']} 条"
    if report['issues']:
        detail += '；需人工处理：' + '；'.join(report['issues'][:3])
    return detail


def create_production_notice(contract_id, header, rows):
    _require_contract(contract_id)
    try:
        return ledger_store.create_production_notice(
            contract_id, header, rows
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError('投产通知编号已存在') from exc


def save_production_notice_draft(notice_id, header, rows):
    _require_notice(notice_id)
    try:
        ledger_store.save_production_notice_draft(
            notice_id, header, rows
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError('投产通知编号已存在') from exc


def transition_production_notice(
    notice_id, action, *, operator='', reason=''
):
    _require_notice(notice_id)
    operations = {
        'issue': lambda: ledger_store.issue_production_notice(
            notice_id, operator
        ),
        'acknowledge': lambda: ledger_store.acknowledge_production_notice(
            notice_id, operator
        ),
        'close': lambda: ledger_store.close_production_notice(
            notice_id, operator
        ),
        'cancel': lambda: ledger_store.cancel_production_notice(
            notice_id, operator, reason
        ),
    }
    operation = operations.get(action)
    if operation is None:
        raise ValueError('投产通知操作无效')

    result = operation()
    suffix = ''
    if isinstance(result, dict):
        count = len(result.get('payment_plan_ids', []))
        suffix = f'，生成 {count} 条动态付款计划'
    return NOTICE_ACTION_MESSAGES[action] + suffix


def revise_production_notice(notice_id, operator=''):
    _require_notice(notice_id)
    return ledger_store.revise_production_notice(notice_id, operator)
