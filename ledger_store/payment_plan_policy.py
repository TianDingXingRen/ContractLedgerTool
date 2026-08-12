"""Shared retention rules for payment-plan execution records."""

from __future__ import annotations


def execution_trace_predicate(alias='p'):
    """Return the SQL predicate that identifies non-deletable plan traces."""
    return f"""(
        COALESCE({alias}.paid_amount_minor, 0) > 0
        OR COALESCE({alias}.paid_amount, 0) > 0
        OR TRIM(COALESCE({alias}.paid_date, '')) != ''
        OR {alias}.payment_status IN ('partial', 'paid')
        OR {alias}.trigger_event_id IS NOT NULL
        OR EXISTS (
            SELECT 1 FROM invoice_allocations ia
             WHERE ia.payment_plan_id = {alias}.id
        )
    )"""


def assert_can_delete(conn, plan_id, contract_id=None):
    """Reject deletion once a plan participates in financial execution."""
    where = 'p.id = ?'
    params = [plan_id]
    if contract_id is not None:
        where += ' AND p.contract_id = ?'
        params.append(contract_id)
    row = conn.execute(
        f"""SELECT p.id, {execution_trace_predicate('p')} AS has_trace
              FROM payment_plans p
             WHERE {where}""",
        params,
    ).fetchone()
    if not row:
        raise ValueError('付款计划不存在或不属于当前合同')
    if row['has_trace']:
        raise ValueError('付款计划已有付款或业务执行记录，为保留审计记录不能删除')


def contract_has_execution_trace(conn, contract_id):
    """Return whether any payment plan under a contract must be retained."""
    return bool(conn.execute(
        f"""SELECT 1
              FROM payment_plans p
             WHERE p.contract_id = ?
               AND {execution_trace_predicate('p')}
             LIMIT 1""",
        (contract_id,),
    ).fetchone())
