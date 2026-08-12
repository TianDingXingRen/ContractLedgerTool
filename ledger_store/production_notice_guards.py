"""Cross-record guards used by production notice state changes."""

from __future__ import annotations


def active_contract(conn, contract_id):
    contract = conn.execute(
        'SELECT * FROM contracts WHERE id = ? AND deleted_at = ?',
        (contract_id, ''),
    ).fetchone()
    if not contract:
        raise ValueError('合同不存在')
    if contract['status'] == 'void':
        raise ValueError('已作废合同不能创建、编辑或签发投产通知')
    return contract


def require_conditional_update(cursor):
    if cursor.rowcount != 1:
        raise ValueError('投产通知状态已变化，请刷新后重试')


def ensure_event_has_no_payment(conn, event_id):
    if not event_id:
        return
    paid = conn.execute(
        """SELECT 1 FROM payment_plans
           WHERE trigger_event_id = ? AND paid_amount_minor > 0 LIMIT 1""",
        (event_id,),
    ).fetchone()
    if paid:
        raise ValueError('该投产通知已发生付款，不能取消或用新版本替代')


def ensure_notice_has_no_invoice_allocations(conn, notice_id):
    allocated = conn.execute(
        """SELECT 1
           FROM invoice_allocations ia
           JOIN invoices i ON i.id = ia.invoice_id
           JOIN production_notices pn ON pn.id = ?
           LEFT JOIN payment_plans pp ON pp.id = ia.payment_plan_id
           WHERE (
               ia.production_notice_id = pn.id
               OR pp.trigger_event_id = pn.payment_trigger_event_id
           )
             AND i.invoice_status = 'valid'
             AND NOT EXISTS (
                 SELECT 1 FROM invoices red
                 WHERE red.original_invoice_id = i.id
                   AND red.invoice_status = 'red'
             )
           LIMIT 1""",
        (notice_id,),
    ).fetchone()
    if allocated:
        raise ValueError('该投产通知已有发票分摊，请先冲销或解除分摊')
