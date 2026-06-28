"""Dashboard and reminder read queries for the contract ledger."""

from datetime import date, timedelta


def next_month_payment_plans(get_conn, row_to_dict, start_date, end_date):
    sql = """
        SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
               c.amount AS contract_amount, c.project_name,
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
            "SELECT status, COUNT(*), COALESCE(SUM(amount),0) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL GROUP BY status"
        ).fetchall()
        total_amount = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL"
        ).fetchone()[0]
    by_status = {row[0]: {'count': row[1], 'amount': row[2]} for row in status_rows}
    return {
        'total': total,
        'by_status': by_status,
        'total_amount': total_amount or 0,
    }


def get_payment_stats(get_conn):
    """Return payment totals for dashboard cards."""
    with get_conn() as conn:
        due = conn.execute(
            """SELECT COALESCE(SUM(p.due_amount),0) FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'confirmed' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
        paid = conn.execute(
            """SELECT COALESCE(SUM(p.paid_amount),0) FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'confirmed' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
        pending = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(p.due_amount),0)
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
        'total_due': due or 0,
        'total_paid': paid or 0,
        'total_unpaid': ((due or 0) - (paid or 0)),
        'pending_count': pending[0] or 0,
        'pending_amount': pending[1] or 0,
        'pending_missing_date': pending_missing_date or 0,
    }


def get_monthly_payments(get_conn, year, month):
    """Return count and remaining amount due for a month."""
    ym = f'{year}-{month:02d}'
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(p.due_amount - COALESCE(p.paid_amount,0)),0)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
                 AND p.confirm_status = 'confirmed'
                 AND p.payment_status != 'paid'
                 AND p.due_date LIKE ?""",
            (ym + '%',)
        ).fetchone()
    return {'count': row[0], 'amount': row[1] or 0}


def get_expiring_contracts(get_conn, row_to_dict, days=30, today=None):
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
    with get_conn() as conn:
        rows = conn.execute(sql, (
            today.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))).fetchall()
    return [row_to_dict(r) for r in rows]


def get_due_soon_payments(get_conn, row_to_dict, days=7, today=None):
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
    with get_conn() as conn:
        rows = conn.execute(sql, (
            today.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))).fetchall()
    return [row_to_dict(r) for r in rows]


def get_recent_contracts(get_conn, row_to_dict, limit=5):
    """Return recent non-deleted contracts."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]
