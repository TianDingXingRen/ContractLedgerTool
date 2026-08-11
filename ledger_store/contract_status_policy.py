"""Cross-cutting invariants for contract lifecycle state changes."""

from __future__ import annotations


def assert_contracts_can_be_voided(conn, contract_ids):
    """Reject voiding contracts that already have financial execution data."""
    normalized_ids = [int(contract_id) for contract_id in contract_ids]
    if not normalized_ids:
        return
    placeholders = ','.join('?' for _ in normalized_ids)
    blocked = conn.execute(
        f"""
        SELECT c.id
          FROM contracts c
         WHERE c.id IN ({placeholders})
           AND (
               EXISTS (
                   SELECT 1 FROM payment_plans p
                    WHERE p.contract_id = c.id
                      AND (
                          p.payment_status = 'paid'
                          OR COALESCE(p.paid_amount_minor, 0) > 0
                      )
               )
               OR EXISTS (
                   SELECT 1 FROM invoice_allocations ia
                    WHERE ia.contract_id = c.id
               )
           )
         LIMIT 1
        """,
        normalized_ids,
    ).fetchone()
    if blocked:
        raise ValueError(
            '合同已有付款或发票分摊，不能直接作废；请先完成冲销流程'
        )
