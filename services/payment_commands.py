"""Application commands for payment plans, rules, and contract serials."""

from __future__ import annotations

import ledger_store
from core.domain_errors import NotFoundError
from ledger_store.contract_serials import MAX_SERIALS_PER_CONTRACT
from utils.generation_utils import can_bulk_confirm_payment


def contract_serial_limit():
    return MAX_SERIALS_PER_CONTRACT


def _require_contract(contract_id):
    contract = ledger_store.get_contract(contract_id)
    if not contract:
        raise NotFoundError('合同记录不存在')
    return contract


def _require_payable_contract(contract_id):
    contract = _require_contract(contract_id)
    if contract.get('status') == 'void':
        raise ValueError('已作废合同不能修改付款数据')
    return contract


def sync_contract_serials(contract_id):
    _require_contract(contract_id)
    ledger_store.sync_contract_serial_range(contract_id)


def save_contract_serials(contract_id, entries):
    _require_contract(contract_id)
    ledger_store.save_contract_serial_amounts(contract_id, entries)


def set_contract_serial_bulk_amount(
    contract_id, bulk_amount, *, blank_only=True
):
    _require_contract(contract_id)
    ledger_store.set_contract_serial_bulk_amount(
        contract_id, bulk_amount, blank_only=blank_only
    )


def set_payment_rule_status(contract_id, rule_id, status):
    _require_payable_contract(contract_id)
    changed = ledger_store.set_payment_rule_confirm_status(
        rule_id, contract_id, status
    )
    if not changed:
        raise NotFoundError('付款规则不存在')


def update_payment_rule(contract_id, rule_id, values):
    _require_payable_contract(contract_id)
    changed = ledger_store.update_payment_rule_manual(
        rule_id, contract_id, values
    )
    if not changed:
        raise NotFoundError('付款规则不存在')


def trigger_payment_rule(contract_id, rule_id, event):
    _require_payable_contract(contract_id)
    ledger_store.create_payment_rule_event_instance(
        contract_id,
        rule_id,
        event['reference_no'],
        event_date=event['event_date'],
        base_amount=event['base_amount'],
        reference_name=event['reference_name'],
    )


def save_payment_plans(contract_id, changes):
    _require_payable_contract(contract_id)
    ledger_store.save_payment_plan_changes(contract_id, changes)


def confirm_all_payment_plans(contract_id):
    _require_payable_contract(contract_id)
    plans = ledger_store.list_payment_plans(
        contract_id=contract_id, confirm_status='pending'
    )
    confirmable_ids = [
        plan['id'] for plan in plans if can_bulk_confirm_payment(plan)
    ]
    if confirmable_ids:
        ledger_store.batch_confirm_plans(confirmable_ids, contract_id)
    return len(confirmable_ids)


def batch_confirm_payment_plans(plan_ids):
    return ledger_store.batch_confirm_plans(plan_ids)


def batch_mark_payment_plans_paid(plan_ids, paid_date):
    return ledger_store.batch_mark_plans_paid(plan_ids, paid_date)


def quick_update_payment_plan(
    plan_id, action, *, paid_date='', paid_amount=None
):
    plan = ledger_store.get_payment_plan(plan_id)
    if not plan:
        raise NotFoundError('付款计划不存在')
    if plan.get('confirm_status') == 'void':
        raise ValueError('已作废的付款计划不能执行快捷操作')
    if plan.get('contract_status') == 'void':
        raise ValueError('已作废合同不能执行付款操作')

    if action == 'confirm':
        values = {'confirm_status': 'confirmed'}
    elif action == 'paid':
        if plan.get('due_amount') is None:
            raise ValueError('缺少应付金额，不能直接标记已付')
        values = {
            'confirm_status': 'confirmed',
            'paid_amount': plan.get('due_amount'),
            'paid_date': paid_date,
        }
    elif action == 'partial':
        if paid_amount is None or paid_amount <= 0:
            raise ValueError('部分付款金额必须大于 0')
        values = {
            'confirm_status': 'confirmed',
            'paid_amount': paid_amount,
            'paid_date': paid_date,
        }
    elif action == 'unpaid':
        values = {'paid_amount': 0, 'paid_date': ''}
    else:
        raise ValueError('快捷操作无效')

    changed = ledger_store.update_payment_plan(
        plan_id, values, require_not_void=True
    )
    if not changed:
        raise NotFoundError('付款计划不存在')
