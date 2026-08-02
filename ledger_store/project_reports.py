"""Project-oriented read queries for the contract ledger."""


def list_project_names(get_conn):
    """Return existing project names, most recently updated first."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT TRIM(project_name) AS project_name, MAX(updated_at) AS last_updated
            FROM contracts
            WHERE TRIM(COALESCE(project_name, '')) != ''
              AND (deleted_at = '' OR deleted_at IS NULL)
            GROUP BY TRIM(project_name)
            ORDER BY last_updated DESC, project_name COLLATE NOCASE
            """
        ).fetchall()
    return [row['project_name'] for row in rows]


def list_project_grouped_contracts(get_conn, row_to_dict, q='', status=''):
    """Return contracts grouped by project_name for the project progress view."""
    clauses = [
        "(c.deleted_at = '' OR c.deleted_at IS NULL)",
        "TRIM(COALESCE(c.project_name, '')) != ''",
    ]
    params = []
    if q:
        like = f'%{q}%'
        clauses.append(
            '(c.contract_no LIKE ? OR c.title LIKE ? OR c.counterparty LIKE ? '
            'OR c.owner LIKE ? OR c.project_name LIKE ? OR c.values_json LIKE ? '
            'OR EXISTS (SELECT 1 FROM payment_plans p WHERE p.contract_id = c.id '
            'AND (p.condition_text LIKE ? OR p.source_text LIKE ? OR p.phase_name LIKE ?)))'
        )
        params.extend([like] * 9)
    if status:
        clauses.append('c.status = ?')
        params.append(status)
    where = ' WHERE ' + ' AND '.join(clauses)
    sql = f"""
        SELECT c.*,
               (SELECT COUNT(*) FROM payment_plans p WHERE p.contract_id = c.id) AS plan_count,
               (SELECT COUNT(*) FROM payment_plans p WHERE p.contract_id = c.id
                  AND p.confirm_status = 'pending') AS pending_count,
               (SELECT COUNT(*) FROM payment_plans p WHERE p.contract_id = c.id
                  AND p.confirm_status = 'confirmed' AND p.payment_status != 'paid') AS payable_count
        FROM contracts c{where}
        ORDER BY c.project_name COLLATE NOCASE, c.created_at DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    contracts = [row_to_dict(r) for r in rows]
    pg_dict = {}
    for contract in contracts:
        project_name = (contract.get('project_name') or '').strip()
        if project_name:
            pg_dict.setdefault(project_name, []).append(contract)
    return sorted(pg_dict.items(), key=lambda item: item[0])


def get_project_progress_stats(get_conn, row_to_dict):
    """Summarize contract signing and payment reach by project."""
    sql = """
        SELECT
            TRIM(c.project_name) AS project_name,
            COUNT(*) AS contract_count,
            SUM(CASE WHEN c.status IN ('signed', 'active', 'completed') THEN 1 ELSE 0 END)
                AS signed_contract_count,
            MIN(CASE WHEN c.status IN ('signed', 'active', 'completed')
                     THEN c.coverage_start END) AS signed_from,
            MAX(CASE WHEN c.status IN ('signed', 'active', 'completed')
                     THEN c.coverage_end END) AS signed_to,
            MAX(CASE WHEN EXISTS (
                    SELECT 1 FROM payment_plans p
                    WHERE p.contract_id = c.id AND p.confirm_status != 'void'
                ) THEN c.coverage_end END) AS planned_to,
            MAX(CASE WHEN EXISTS (
                    SELECT 1 FROM payment_plans p
                    WHERE p.contract_id = c.id
                      AND p.confirm_status = 'confirmed'
                      AND (COALESCE(p.paid_amount_minor, 0) > 0
                           OR p.payment_status IN ('partial', 'paid'))
                ) THEN c.coverage_end END) AS paid_to
        FROM contracts c
        WHERE TRIM(COALESCE(c.project_name, '')) != ''
          AND c.status != 'void'
          AND (c.deleted_at = '' OR c.deleted_at IS NULL)
        GROUP BY TRIM(c.project_name)
        ORDER BY MAX(COALESCE(c.coverage_end, 0)) DESC,
                 TRIM(c.project_name) COLLATE NOCASE
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [row_to_dict(row) for row in rows]
