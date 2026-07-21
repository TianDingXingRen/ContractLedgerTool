"""List and search queries for contracts and payment plans."""


def list_contracts(
    get_conn,
    row_to_dict,
    q='',
    status='',
    page=1,
    per_page=20,
    include_deleted=False,
    deleted_only=False,
):
    """Return paged contracts with payment-plan counters."""
    base_sql = "FROM contracts c"
    clauses = []
    params = []
    if deleted_only:
        clauses.append("(c.deleted_at != '' AND c.deleted_at IS NOT NULL)")
    elif not include_deleted:
        clauses.append("(c.deleted_at = '' OR c.deleted_at IS NULL)")
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
    where = ''
    if clauses:
        where = ' WHERE ' + ' AND '.join(clauses)

    count_sql = f'SELECT COUNT(*) {base_sql}{where}'
    offset = max(0, (page - 1) * per_page)
    sql = f"""
        SELECT c.*,
               (SELECT COUNT(*) FROM payment_plans p
                WHERE p.contract_id = c.id) AS plan_count,
               (SELECT COUNT(*) FROM payment_plans p
                WHERE p.contract_id = c.id
                  AND p.confirm_status = 'pending') AS pending_count,
               (SELECT COUNT(*) FROM payment_plans p
                WHERE p.contract_id = c.id
                  AND p.confirm_status = 'confirmed'
                  AND p.payment_status != 'paid') AS payable_count
        FROM contracts c
        {where}
        ORDER BY c.created_at DESC
        LIMIT ? OFFSET ?
    """
    with get_conn() as conn:
        total = conn.execute(count_sql, params).fetchone()[0]
        rows = conn.execute(sql, [*params, per_page, offset]).fetchall()
    return {
        'rows': [row_to_dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page or 1,
    }


def iter_contracts(
    get_conn, row_to_dict, q='', status='', batch_size=500,
    include_deleted=False, deleted_only=False,
):
    """Yield contracts in bounded pages for large exports."""
    page = 1
    while True:
        result = list_contracts(
            get_conn, row_to_dict, q=q, status=status, page=page,
            per_page=batch_size, include_deleted=include_deleted,
            deleted_only=deleted_only,
        )
        yield from result['rows']
        if page >= result['pages']:
            return
        page += 1


def list_payment_plans(
    get_conn,
    row_to_dict,
    contract_id=None,
    confirm_status='',
    payment_status='',
    start_date='',
    end_date='',
    project_name='',
    page=0,
    per_page=20,
    limit=0,
):
    base_sql = """
        FROM payment_plans p
        JOIN contracts c ON c.id = p.contract_id
    """
    clauses = ["(c.deleted_at = '' OR c.deleted_at IS NULL)"]
    params = []
    if contract_id:
        clauses.append('p.contract_id = ?')
        params.append(contract_id)
    if confirm_status:
        clauses.append('p.confirm_status = ?')
        params.append(confirm_status)
    if payment_status:
        clauses.append('p.payment_status = ?')
        params.append(payment_status)
    if start_date:
        clauses.append('p.due_date >= ?')
        params.append(start_date)
    if end_date:
        clauses.append('p.due_date <= ?')
        params.append(end_date)
    if project_name:
        clauses.append('c.project_name = ?')
        params.append(project_name)
    where = ''
    if clauses:
        where = ' WHERE ' + ' AND '.join(clauses)

    if page > 0:
        count_sql = f'SELECT COUNT(*) {base_sql}{where}'
        offset = max(0, (page - 1) * per_page)
        sql = f"""
            SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
                   c.amount_minor AS contract_amount_minor, c.project_name,
                   c.coverage_start, c.coverage_end
            {base_sql}{where}
            ORDER BY COALESCE(p.due_date, '9999-12-31'), p.id
            LIMIT ? OFFSET ?
        """
        with get_conn() as conn:
            total = conn.execute(count_sql, params).fetchone()[0]
            rows = conn.execute(sql, [*params, per_page, offset]).fetchall()
        return {
            'rows': [row_to_dict(r) for r in rows],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page or 1,
        }

    sql = f"""
        SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
               c.amount_minor AS contract_amount_minor, c.project_name,
               c.coverage_start, c.coverage_end
        {base_sql}{where}
        ORDER BY COALESCE(p.due_date, '9999-12-31'), p.id
    """
    query_params = list(params)
    if limit:
        sql += ' LIMIT ?'
        query_params.append(max(1, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(sql, query_params).fetchall()
    return [row_to_dict(r) for r in rows]
