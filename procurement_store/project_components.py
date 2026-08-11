"""Project item, supplier, and file persistence helpers."""

from contextlib import nullcontext

from database.connection_factory import begin_immediate


def list_project_items(get_conn, project_id):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM project_items WHERE project_id = ? ORDER BY line_no, id',
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_project_item(get_conn, audit, now_func, project_id, data):
    now = now_func()
    with get_conn() as conn:
        line_no = data.get('line_no') or conn.execute(
            'SELECT COALESCE(MAX(line_no), 0) + 1 FROM project_items WHERE project_id = ?',
            (project_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO project_items
               (project_id, line_no, item_name, spec_model, drawing_no, quantity_text, unit,
                required_delivery_date, technical_requirement, remark, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, line_no, data['item_name'], data.get('spec_model') or '',
             data.get('drawing_no') or '', data['quantity_text'], data['unit'],
             data.get('required_delivery_date') or '',
             data.get('technical_requirement') or '', data.get('remark') or '', now, now),
        )
        item_id = cur.lastrowid
        audit(conn, 'project_item', item_id, 'create', after=data)
        return item_id


def add_project_items_bulk(get_conn, audit, now_func, project_id, items):
    now = now_func()
    created = []
    with get_conn() as conn:
        next_line = conn.execute(
            'SELECT COALESCE(MAX(line_no), 0) + 1 FROM project_items WHERE project_id = ?',
            (project_id,),
        ).fetchone()[0]
        for offset, data in enumerate(items):
            cur = conn.execute(
                """INSERT INTO project_items
                   (project_id, line_no, item_name, spec_model, drawing_no, quantity_text, unit,
                    required_delivery_date, technical_requirement, remark, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (project_id, next_line + offset, data['item_name'], data.get('spec_model') or '',
                 data.get('drawing_no') or '', data['quantity_text'], data['unit'],
                 data.get('required_delivery_date') or '', data.get('technical_requirement') or '',
                 data.get('remark') or '', now, now),
            )
            created.append(cur.lastrowid)
        audit(conn, 'project', project_id, 'bulk_add_items', after={'count': len(created)})
    return created


def get_project_item(get_conn, row_to_dict, item_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM project_items WHERE id = ?', (item_id,)).fetchone()
    return row_to_dict(row)


def update_project_item(get_conn, audit, now_func, project_id, item_id, data):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM project_items WHERE id = ? AND project_id = ?',
            (item_id, project_id),
        ).fetchone()
        if not row:
            raise ValueError('采购明细不存在')
        before = dict(row)
        conn.execute(
            """UPDATE project_items SET item_name = ?, spec_model = ?, drawing_no = ?,
                      quantity_text = ?, unit = ?, required_delivery_date = ?,
                      technical_requirement = ?, remark = ?, updated_at = ?
               WHERE id = ?""",
            (data['item_name'], data.get('spec_model') or '', data.get('drawing_no') or '',
             data['quantity_text'], data['unit'], data.get('required_delivery_date') or '',
             data.get('technical_requirement') or '', data.get('remark') or '',
             now_func(), item_id),
        )
        audit(conn, 'project_item', item_id, 'update', before=before, after=data)


def delete_project_item(get_conn, audit, project_id, item_id):
    with get_conn() as conn:
        used = conn.execute(
            'SELECT 1 FROM supplier_quote_items WHERE project_item_id = ? LIMIT 1',
            (item_id,),
        ).fetchone()
        if used:
            raise ValueError('该明细已有供应商报价，不能删除')
        row = conn.execute(
            'SELECT * FROM project_items WHERE id = ? AND project_id = ?',
            (item_id, project_id),
        ).fetchone()
        if not row:
            raise ValueError('采购明细不存在')
        conn.execute('DELETE FROM project_items WHERE id = ?', (item_id,))
        audit(conn, 'project_item', item_id, 'delete', before=dict(row))


def list_project_suppliers(get_conn, project_id):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM project_suppliers WHERE project_id = ? ORDER BY id',
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_supplier(get_conn, row_to_dict, supplier_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM project_suppliers WHERE id = ?', (supplier_id,)
        ).fetchone()
    return row_to_dict(row)


def update_project_supplier(
    get_conn, audit, now_func, normalize_name, project_id, supplier_id, data
):
    name = str(data['supplier_name']).strip()
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM project_suppliers WHERE id = ? AND project_id = ?',
            (supplier_id, project_id),
        ).fetchone()
        if not row:
            raise ValueError('候选供应商不存在')
        before = dict(row)
        conn.execute(
            """UPDATE project_suppliers SET supplier_name = ?, normalized_name = ?,
                      contact_person = ?, contact_phone = ?, email = ?,
                      direct_support_experience = ?, aerospace_support_experience = ?,
                      qualifications = ?, remark = ?, updated_at = ?
               WHERE id = ?""",
            (name, normalize_name(name), data.get('contact_person') or '',
             data.get('contact_phone') or '', data.get('email') or '',
             data.get('direct_support_experience') or '',
             data.get('aerospace_support_experience') or '',
             data.get('qualifications') or '', data.get('remark') or '',
             now_func(), supplier_id),
        )
        audit(conn, 'project_supplier', supplier_id, 'update', before=before, after=data)


def add_project_supplier(
    get_conn, audit, now_func, normalize_name, project_id, data
):
    now = now_func()
    name = str(data['supplier_name']).strip()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO project_suppliers
               (project_id, supplier_name, normalized_name, contact_person, contact_phone,
                email, direct_support_experience, aerospace_support_experience,
                qualifications, invite_status, quote_status, remark, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, name, normalize_name(name), data.get('contact_person') or '',
             data.get('contact_phone') or '', data.get('email') or '',
             data.get('direct_support_experience') or '',
             data.get('aerospace_support_experience') or '',
             data.get('qualifications') or '',
             data.get('invite_status') or 'pending', data.get('quote_status') or 'pending',
             data.get('remark') or '', now, now),
        )
        supplier_id = cur.lastrowid
        audit(conn, 'project_supplier', supplier_id, 'create', after=data)
        return supplier_id


def delete_project_supplier(get_conn, audit, project_id, supplier_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM project_suppliers WHERE id = ? AND project_id = ?',
            (supplier_id, project_id),
        ).fetchone()
        if not row:
            raise ValueError('候选供应商不存在')
        if conn.execute(
            'SELECT 1 FROM supplier_quotes WHERE supplier_id = ? LIMIT 1',
            (supplier_id,),
        ).fetchone():
            raise ValueError('该供应商已有确认报价，不能删除')
        if conn.execute(
            'SELECT 1 FROM negotiation_commitments WHERE supplier_id = ? LIMIT 1',
            (supplier_id,),
        ).fetchone():
            raise ValueError('该供应商已有谈判记录，不能删除')

        paths = {
            item[0]
            for item in conn.execute(
                """SELECT relative_path FROM quote_import_jobs WHERE supplier_id = ?
                   UNION
                   SELECT relative_path FROM quote_mapping_jobs WHERE supplier_id = ?""",
                (supplier_id, supplier_id),
            ).fetchall()
            if item[0]
        }
        conn.execute('DELETE FROM quote_import_jobs WHERE supplier_id = ?', (supplier_id,))
        conn.execute('DELETE FROM quote_mapping_jobs WHERE supplier_id = ?', (supplier_id,))
        conn.execute('DELETE FROM project_suppliers WHERE id = ?', (supplier_id,))
        audit(
            conn, 'project_supplier', supplier_id, 'delete', before=dict(row),
            after={'removed_temporary_quote_files': len(paths)},
        )
        return sorted(paths)


def register_project_file(
    get_conn, now_func, project_id, file_type, relative_path,
    original_name='', sha256='', size_bytes=0, *, connection=None,
):
    manager = nullcontext(connection) if connection is not None else get_conn()
    with manager as conn:
        begin_immediate(conn)
        existing = conn.execute(
            'SELECT id FROM project_files WHERE project_id = ? AND file_type = ? AND relative_path = ?',
            (project_id, file_type, relative_path),
        ).fetchone()
        if existing:
            return existing[0]
        version = conn.execute(
            'SELECT COALESCE(MAX(version), 0) + 1 FROM project_files WHERE project_id = ? AND file_type = ?',
            (project_id, file_type),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO project_files
               (project_id, file_type, relative_path, original_name, sha256, size_bytes, version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, file_type, relative_path, original_name, sha256,
             int(size_bytes or 0), version, now_func()),
        )
        return cur.lastrowid


def list_project_files(get_conn, project_id):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM project_files WHERE project_id = ? ORDER BY created_at DESC, id DESC',
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_file(get_conn, row_to_dict, file_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM project_files WHERE id = ?', (file_id,)).fetchone()
    return row_to_dict(row)
