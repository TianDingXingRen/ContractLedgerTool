"""Dashboard and reminder read queries for the contract ledger."""

from datetime import date, timedelta


def next_month_payment_plans(get_conn, row_to_dict, start_date, end_date):
    sql = """
        SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
               c.amount_minor AS contract_amount_minor, c.project_name,
               c.coverage_start, c.coverage_end
        FROM payment_plans p
        JOIN contracts c ON c.id = p.contract_id
        WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
          AND p.confirm_status = 'confirmed'
          AND p.payment_status != 'paid'
          AND p.due_date >= ?
          AND p.due_date <= ?
        ORDER BY p.due_date, c.counterparty, c.contract_no, p.id
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (start_date, end_date)).fetchall()
    return [row_to_dict(r) for r in rows]


def get_contract_stats(get_conn):
    """Return contract totals grouped for dashboard cards."""
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL"
        ).fetchone()[0]
        status_rows = conn.execute(
            "SELECT status, COUNT(*), COALESCE(SUM(amount_minor),0) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL GROUP BY status"
        ).fetchall()
        total_amount = conn.execute(
            "SELECT COALESCE(SUM(amount_minor),0) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL"
        ).fetchone()[0]
    by_status = {
        row[0]: {'count': row[1], 'amount': float(row[2] or 0) / 100}
        for row in status_rows
    }
    return {
        'total': total,
        'by_status': by_status,
        'total_amount': float(total_amount or 0) / 100,
    }


def get_payment_stats(get_conn):
    """Return payment totals for dashboard cards."""
    with get_conn() as conn:
        due = conn.execute(
            """SELECT COALESCE(SUM(p.due_amount_minor),0) FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'confirmed' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
        paid = conn.execute(
            """SELECT COALESCE(SUM(p.paid_amount_minor),0) FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'confirmed' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
        pending = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(p.due_amount_minor),0)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'pending' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()
        pending_missing_date = conn.execute(
            """SELECT COUNT(*)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'pending'
                 AND COALESCE(p.due_date, '') = ''
                 AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
    return {
        'total_due': float(due or 0) / 100,
        'total_paid': float(paid or 0) / 100,
        'total_unpaid': float((due or 0) - (paid or 0)) / 100,
        'pending_count': pending[0] or 0,
        'pending_amount': float(pending[1] or 0) / 100,
        'pending_missing_date': pending_missing_date or 0,
    }


def get_monthly_payments(get_conn, year, month):
    """Return count and remaining amount due for a month."""
    ym = f'{year}-{month:02d}'
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(p.due_amount_minor - COALESCE(p.paid_amount_minor,0)),0)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
                 AND p.confirm_status = 'confirmed'
                 AND p.payment_status != 'paid'
                 AND p.due_date LIKE ?""",
            (ym + '%',)
        ).fetchone()
    return {'count': row[0], 'amount': float(row[1] or 0) / 100}


def get_expiring_contracts(get_conn, row_to_dict, days=30, today=None, limit=0):
    """Return signed/active contracts expiring within N days."""
    today = today or date.today()
    end = today + timedelta(days=days)
    sql = """
        SELECT * FROM contracts
        WHERE expiry_date != '' AND expiry_date IS NOT NULL
          AND status IN ('signed', 'active')
          AND (deleted_at = '' OR deleted_at IS NULL)
          AND expiry_date >= ? AND expiry_date <= ?
        ORDER BY expiry_date
    """
    params = [today.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')]
    if limit:
        sql += ' LIMIT ?'
        params.append(max(1, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]


def get_due_soon_payments(get_conn, row_to_dict, days=7, today=None, limit=0):
    """Return confirmed unpaid payment plans due within N days."""
    today = today or date.today()
    end = today + timedelta(days=days)
    sql = """
        SELECT p.*, c.contract_no, c.title AS contract_title,
               c.counterparty, c.owner, c.project_name,
               c.coverage_start, c.coverage_end
        FROM payment_plans p
        JOIN contracts c ON c.id = p.contract_id
        WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
          AND p.confirm_status = 'confirmed'
          AND p.payment_status != 'paid'
          AND p.due_date >= ? AND p.due_date <= ?
        ORDER BY p.due_date
    """
    params = [today.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')]
    if limit:
        sql += ' LIMIT ?'
        params.append(max(1, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]


def get_recent_contracts(get_conn, row_to_dict, limit=5):
    """Return recent non-deleted contracts."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_contract_workspace_summary(get_conn, contract_id, today=None):
    """Return compact, read-only execution totals for a contract workspace."""
    today_text = (today or date.today()).strftime('%Y-%m-%d')
    with get_conn() as conn:
        contract = conn.execute(
            'SELECT amount_minor FROM contracts WHERE id = ?', (contract_id,)
        ).fetchone()
        production = conn.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(CASE WHEN status IN ('issued','acknowledged','closed')
                                        THEN total_qty ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN status IN ('issued','acknowledged','closed')
                                        THEN total_amount_minor ELSE 0 END), 0)
                 FROM production_notices WHERE contract_id = ?""",
            (contract_id,),
        ).fetchone()
        payments = conn.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(due_amount_minor), 0),
                      COALESCE(SUM(paid_amount_minor), 0),
                      COALESCE(SUM(MAX(COALESCE(due_amount_minor, 0) -
                                           COALESCE(paid_amount_minor, 0), 0)), 0),
                      SUM(CASE WHEN payment_status != 'paid'
                                    AND COALESCE(due_date, '') != ''
                                    AND due_date < ? THEN 1 ELSE 0 END)
                 FROM payment_plans
                WHERE contract_id = ? AND confirm_status = 'confirmed'""",
            (today_text, contract_id),
        ).fetchone()
        review = conn.execute(
            """SELECT SUM(CASE WHEN confirm_status = 'pending' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN parse_status IN ('conflict','unsupported','partial')
                               THEN 1 ELSE 0 END)
                 FROM payment_rules WHERE contract_id = ?""",
            (contract_id,),
        ).fetchone()
        invoices = conn.execute(
            """WITH linked AS (
                   SELECT DISTINCT i.id, i.total_amount_minor, i.review_status
                     FROM invoices i
                     JOIN invoice_allocations ia ON ia.invoice_id = i.id
                    WHERE ia.contract_id = ?
                      AND i.invoice_status = 'valid'
                      AND NOT EXISTS (
                          SELECT 1 FROM invoices red
                           WHERE red.original_invoice_id = i.id
                             AND red.invoice_status = 'red'
                      )
               )
               SELECT COUNT(*),
                      COALESCE((SELECT SUM(ia.allocated_amount_minor)
                                  FROM invoice_allocations ia
                                  JOIN linked l ON l.id = ia.invoice_id
                                 WHERE ia.contract_id = ?), 0),
                      COALESCE(SUM(MAX(total_amount_minor -
                          COALESCE((SELECT SUM(a.allocated_amount_minor)
                                      FROM invoice_allocations a
                                     WHERE a.invoice_id = linked.id), 0), 0)), 0),
                      SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END)
                 FROM linked""",
            (contract_id, contract_id),
        ).fetchone()
    return {
        'contract_amount': float((contract[0] if contract else 0) or 0) / 100,
        'production_count': production[0] or 0,
        'production_qty': production[1] or 0,
        'production_amount': float(production[2] or 0) / 100,
        'confirmed_plan_count': payments[0] or 0,
        'payment_due': float(payments[1] or 0) / 100,
        'payment_paid': float(payments[2] or 0) / 100,
        'payment_unpaid': float(payments[3] or 0) / 100,
        'overdue_count': payments[4] or 0,
        'pending_rule_count': review[0] or 0,
        'review_rule_count': review[1] or 0,
        'invoice_count': invoices[0] or 0,
        'invoice_allocated': float(invoices[1] or 0) / 100,
        'invoice_unallocated': float(invoices[2] or 0) / 100,
        'pending_invoice_count': invoices[3] or 0,
    }


def summarize_payment_plans(
    get_conn, *, confirm_status='', payment_status='', start_date='',
    end_date='', project_name='', today=None,
):
    clauses = ["(c.deleted_at = '' OR c.deleted_at IS NULL)"]
    params = []
    for field, value in (
        ('p.confirm_status', confirm_status), ('p.payment_status', payment_status),
        ('c.project_name', project_name),
    ):
        if value:
            clauses.append(f'{field} = ?')
            params.append(value)
    if start_date:
        clauses.append('p.due_date >= ?')
        params.append(start_date)
    if end_date:
        clauses.append('p.due_date <= ?')
        params.append(end_date)
    today_text = (today or date.today()).strftime('%Y-%m-%d')
    where = ' AND '.join(clauses)
    with get_conn() as conn:
        row = conn.execute(
            f"""SELECT COUNT(*),
                       SUM(CASE WHEN p.payment_status != 'paid' THEN 1 ELSE 0 END),
                       COALESCE(SUM(CASE WHEN p.payment_status != 'paid'
                         THEN MAX(COALESCE(p.due_amount_minor,0) - COALESCE(p.paid_amount_minor,0),0)
                         ELSE 0 END),0),
                       SUM(CASE WHEN p.payment_status != 'paid' AND COALESCE(p.due_date,'') != ''
                                     AND p.due_date < ? THEN 1 ELSE 0 END),
                       COALESCE(SUM(CASE WHEN p.payment_status != 'paid' AND COALESCE(p.due_date,'') != ''
                                     AND p.due_date < ?
                         THEN MAX(COALESCE(p.due_amount_minor,0) - COALESCE(p.paid_amount_minor,0),0)
                         ELSE 0 END),0)
                  FROM payment_plans p JOIN contracts c ON c.id = p.contract_id
                 WHERE {where}""",
            [today_text, today_text, *params],
        ).fetchone()
    return {
        'count': row[0] or 0,
        'unpaid_count': row[1] or 0,
        'unpaid_amount': float(row[2] or 0) / 100,
        'overdue_count': row[3] or 0,
        'overdue_amount': float(row[4] or 0) / 100,
    }
