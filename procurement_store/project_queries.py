"""Project read queries for procurement workflows."""

import json


def get_project(get_conn, row_to_dict, project_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM project_items i WHERE i.project_id = p.id) item_count,
                      (SELECT COUNT(*) FROM project_suppliers s WHERE s.project_id = p.id) supplier_count,
                      (SELECT COUNT(*) FROM supplier_quotes q WHERE q.project_id = p.id AND q.status = 'confirmed') quote_count
               FROM procurement_projects p WHERE p.id = ?""",
            (project_id,),
        ).fetchone()
    return row_to_dict(row)


def list_projects(get_conn, row_to_dict, status='', q='', page=1, per_page=20):
    clauses = []
    params = []
    if status:
        clauses.append('p.status = ?')
        params.append(status)
    if q:
        clauses.append('(p.project_no LIKE ? OR p.project_name LIKE ? OR p.owner LIKE ?)')
        token = f'%{q}%'
        params.extend([token, token, token])
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    page = max(1, int(page))
    per_page = max(1, min(100, int(per_page)))
    with get_conn() as conn:
        total = conn.execute(
            f'SELECT COUNT(*) FROM procurement_projects p{where}', params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM project_items i WHERE i.project_id = p.id) item_count,
                       (SELECT COUNT(*) FROM project_suppliers s WHERE s.project_id = p.id) supplier_count,
                       (SELECT COUNT(*) FROM supplier_quotes sq WHERE sq.project_id = p.id AND sq.status = 'confirmed') quote_count
                FROM procurement_projects p{where}
                ORDER BY p.updated_at DESC, p.id DESC LIMIT ? OFFSET ?""",
            (*params, per_page, (page - 1) * per_page),
        ).fetchall()
    return {
        'rows': [row_to_dict(row) for row in rows],
        'total': total,
        'page': page,
        'pages': max(1, (total + per_page - 1) // per_page),
    }


def list_project_audit_events(get_conn, project_id, actions=None):
    params = [project_id]
    where = "entity_type = 'project' AND entity_id = ?"
    if actions:
        placeholders = ','.join('?' for _ in actions)
        where += f' AND action IN ({placeholders})'
        params.extend(actions)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM procurement_audit_events
                WHERE {where}
                ORDER BY created_at DESC, id DESC""",
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key in ('before_json', 'after_json'):
            try:
                item[key.replace('_json', '')] = json.loads(item.get(key) or '{}')
            except json.JSONDecodeError:
                item[key.replace('_json', '')] = {}
        result.append(item)
    return result
