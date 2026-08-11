"""Quote import, mapping, and quote read helpers."""

import json

from database.connection_factory import begin_immediate
from utils.money import SQLITE_MAX_INTEGER

from . import project_components


def _quote_is_award_locked(conn, quote_id):
    return conn.execute(
        """SELECT 1 FROM award_recommendations WHERE quote_id = ?
           UNION ALL
           SELECT 1 FROM award_recommendation_items
           WHERE quote_id = ?
              OR quote_item_id IN (
                  SELECT id FROM supplier_quote_items WHERE quote_id = ?
              )
           LIMIT 1""",
        (quote_id, quote_id, quote_id),
    ).fetchone() is not None


def _invalidate_comparisons(conn, project_id):
    count = conn.execute(
        'SELECT COUNT(*) FROM comparison_runs WHERE project_id = ?',
        (project_id,),
    ).fetchone()[0]
    conn.execute('DELETE FROM comparison_runs WHERE project_id = ?', (project_id,))
    return int(count or 0)


def create_import_job(get_conn, now_func, data):
    with get_conn() as conn:
        duplicate = conn.execute(
            """SELECT id FROM quote_import_jobs
               WHERE project_id = ? AND file_sha256 = ? AND status = 'confirmed' LIMIT 1""",
            (data['project_id'], data['file_sha256']),
        ).fetchone()
        if duplicate:
            raise ValueError(f'该报价文件已经导入（任务 #{duplicate[0]}）')
        cur = conn.execute(
            """INSERT INTO quote_import_jobs
               (project_id, supplier_id, quote_round, original_name, relative_path, file_sha256,
                parser_version, payload_json, errors_json, warnings_json, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data['project_id'], data['supplier_id'], data['quote_round'], data['original_name'],
             data['relative_path'], data['file_sha256'], data.get('parser_version') or '1.0',
             json.dumps(data.get('payload') or {}, ensure_ascii=False),
             json.dumps(data.get('errors') or [], ensure_ascii=False),
             json.dumps(data.get('warnings') or [], ensure_ascii=False),
             'invalid' if data.get('errors') else 'parsed', now_func()),
        )
        return cur.lastrowid


def get_import_job(get_conn, row_to_dict, job_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT j.*, p.project_no, p.project_name, s.supplier_name
               FROM quote_import_jobs j
               JOIN procurement_projects p ON p.id = j.project_id
               JOIN project_suppliers s ON s.id = j.supplier_id
               WHERE j.id = ?""", (job_id,),
        ).fetchone()
    result = row_to_dict(row)
    if result:
        for source, target in [
            ('payload_json', 'payload'),
            ('errors_json', 'errors'),
            ('warnings_json', 'warnings'),
        ]:
            result[target] = json.loads(
                result.get(source) or ('{}' if target == 'payload' else '[]')
            )
    return result


def create_mapping_job(get_conn, now_func, data):
    now = now_func()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO quote_mapping_jobs
               (project_id, supplier_id, quote_round, source_type, original_name,
                relative_path, file_sha256, source_json, column_map_json,
                metadata_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', '{}', 'mapping', ?, ?)""",
            (data['project_id'], data['supplier_id'], data['quote_round'], data['source_type'],
             data['original_name'], data['relative_path'], data['file_sha256'],
             json.dumps(data['source'], ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def get_mapping_job(get_conn, row_to_dict, job_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT j.*, p.project_no, p.project_name, s.supplier_name
               FROM quote_mapping_jobs j
               JOIN procurement_projects p ON p.id = j.project_id
               JOIN project_suppliers s ON s.id = j.supplier_id
               WHERE j.id = ?""", (job_id,),
        ).fetchone()
    result = row_to_dict(row)
    if result:
        result['source'] = json.loads(result['source_json'])
        result['column_map'] = json.loads(result['column_map_json'] or '{}')
        result['metadata'] = json.loads(result['metadata_json'] or '{}')
    return result


def update_mapping_job(get_conn, now_func, job_id, column_map, metadata, status='parsed'):
    with get_conn() as conn:
        conn.execute(
            """UPDATE quote_mapping_jobs SET column_map_json = ?, metadata_json = ?,
                      status = ?, updated_at = ? WHERE id = ?""",
            (json.dumps(column_map, ensure_ascii=False),
             json.dumps(metadata, ensure_ascii=False), status, now_func(), job_id),
        )


def mark_mapping_job_confirmed(get_conn, now_func, job_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE quote_mapping_jobs SET status = 'confirmed', updated_at = ? WHERE id = ?",
            (now_func(), job_id),
        )


def confirm_import_job(get_conn, audit, now_func, job_id):
    now = now_func()
    with get_conn() as conn:
        # Serialize the status check, project-file version allocation, and
        # quote creation.  Concurrent confirmations then observe a committed
        # job state instead of both acting on the same parsed snapshot.
        begin_immediate(conn)
        job_row = conn.execute(
            'SELECT * FROM quote_import_jobs WHERE id = ?', (job_id,)
        ).fetchone()
        if not job_row:
            raise ValueError('报价导入任务不存在')
        job = dict(job_row)
        if job['status'] == 'confirmed':
            quote = conn.execute(
                'SELECT id FROM supplier_quotes WHERE import_job_id = ?', (job_id,)
            ).fetchone()
            return quote[0] if quote else None
        if job['status'] != 'parsed' or json.loads(job['errors_json'] or '[]'):
            raise ValueError('报价存在解析错误，不能确认导入')
        if conn.execute(
            """SELECT 1 FROM supplier_quotes
               WHERE project_id = ? AND supplier_id = ? AND quote_round = ?""",
            (job['project_id'], job['supplier_id'], job['quote_round']),
        ).fetchone():
            raise ValueError('该供应商当前报价轮次已存在')

        payload = json.loads(job['payload_json'])
        header = payload['header']
        file_id = project_components.register_project_file(
            get_conn,
            now_func,
            job['project_id'],
            'supplier_quote',
            job['relative_path'],
            original_name=job['original_name'],
            sha256=job['file_sha256'],
            size_bytes=int(payload.get('size_bytes') or 0),
            connection=conn,
        )
        cur = conn.execute(
            """INSERT INTO supplier_quotes
               (project_id, supplier_id, quote_round, quote_date, quote_valid_until,
                total_amount_minor, currency, tax_rate_bps, price_basis, delivery_period,
                payment_terms, warranty_period, package_transport, technical_deviation,
                commercial_deviation, original_file_id, import_job_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?)""",
            (job['project_id'], job['supplier_id'], job['quote_round'], header.get('quote_date') or '',
             header.get('quote_valid_until') or '', int(header['total_amount_minor']),
             header.get('currency') or 'CNY', header.get('tax_rate_bps'),
             header.get('price_basis') or 'tax_inclusive', header.get('delivery_period') or '',
             header.get('payment_terms') or '', header.get('warranty_period') or '',
             header.get('package_transport') or '', header.get('technical_deviation') or '',
             header.get('commercial_deviation') or '', file_id, job_id, now, now),
        )
        quote_id = cur.lastrowid
        for item in payload['items']:
            conn.execute(
                """INSERT INTO supplier_quote_items
                   (quote_id, project_item_id, line_no, item_name, spec_model, drawing_no,
                    quantity_text, unit, unit_price_minor, amount_minor, delivery_period,
                    technical_deviation, commercial_deviation, remark, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (quote_id, item['project_item_id'], item['line_no'], item['item_name'],
                 item.get('spec_model') or '', item.get('drawing_no') or '', item['quantity_text'],
                 item['unit'], int(item['unit_price_minor']), int(item['amount_minor']),
                 item.get('delivery_period') or '', item.get('technical_deviation') or '',
                 item.get('commercial_deviation') or '', item.get('remark') or '', now),
            )
        conn.execute(
            "UPDATE quote_import_jobs SET status = 'confirmed', confirmed_at = ? WHERE id = ?",
            (now, job_id),
        )
        conn.execute(
            "UPDATE project_suppliers SET quote_status = 'received', updated_at = ? WHERE id = ?",
            (now, job['supplier_id']),
        )
        conn.execute(
            """UPDATE procurement_projects
               SET status = CASE WHEN status IN ('draft','documents_ready','inquiry_sent') THEN 'quotes_received' ELSE status END,
                   updated_at = ? WHERE id = ?""", (now, job['project_id']),
        )
        audit(conn, 'supplier_quote', quote_id, 'confirm_import', after={'import_job_id': job_id})
        return quote_id


def list_quotes(get_conn, project_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.*, s.supplier_name,
                      (SELECT COUNT(*) FROM supplier_quote_items qi WHERE qi.quote_id = q.id) item_count,
                      (EXISTS(SELECT 1 FROM award_recommendations a WHERE a.quote_id = q.id)
                       OR EXISTS(SELECT 1 FROM award_recommendation_items ai
                                 WHERE ai.quote_id = q.id
                                    OR ai.quote_item_id IN (
                                        SELECT id FROM supplier_quote_items WHERE quote_id = q.id
                                    ))) is_locked
               FROM supplier_quotes q JOIN project_suppliers s ON s.id = q.supplier_id
               WHERE q.project_id = ? ORDER BY q.quote_round DESC, s.supplier_name""", (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_quotes(get_conn, project_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.*, s.supplier_name
               FROM supplier_quotes q
               JOIN project_suppliers s ON s.id = q.supplier_id
               JOIN (
                   SELECT supplier_id, MAX(quote_round) max_round
                   FROM supplier_quotes WHERE project_id = ? AND status = 'confirmed'
                   GROUP BY supplier_id
               ) latest ON latest.supplier_id = q.supplier_id AND latest.max_round = q.quote_round
               WHERE q.project_id = ? AND q.status = 'confirmed'
               ORDER BY s.supplier_name""", (project_id, project_id),
        ).fetchall()
    return [dict(row) for row in rows]


def get_quote(get_conn, row_to_dict, quote_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT q.*, s.supplier_name,
                      (EXISTS(SELECT 1 FROM award_recommendations a WHERE a.quote_id = q.id)
                       OR EXISTS(SELECT 1 FROM award_recommendation_items ai
                                 WHERE ai.quote_id = q.id
                                    OR ai.quote_item_id IN (
                                        SELECT id FROM supplier_quote_items WHERE quote_id = q.id
                                    ))) is_locked
               FROM supplier_quotes q
               JOIN project_suppliers s ON s.id = q.supplier_id WHERE q.id = ?""",
            (quote_id,),
        ).fetchone()
    return row_to_dict(row)


def get_quote_items(get_conn, quote_id):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM supplier_quote_items WHERE quote_id = ? ORDER BY line_no, id',
            (quote_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_quote(get_conn, audit, now_func, quote_id, header, items):
    now = now_func()
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM supplier_quotes WHERE id = ?', (quote_id,)
        ).fetchone()
        if not row:
            raise ValueError('供应商报价不存在')
        if _quote_is_award_locked(conn, quote_id):
            raise ValueError('该报价已用于成交建议，不能编辑')

        stored_items = conn.execute(
            'SELECT * FROM supplier_quote_items WHERE quote_id = ? ORDER BY line_no, id',
            (quote_id,),
        ).fetchall()
        stored_by_id = {item['id']: dict(item) for item in stored_items}
        submitted_by_id = {int(item['id']): item for item in items}
        if len(submitted_by_id) != len(items) or set(stored_by_id) != set(submitted_by_id):
            raise ValueError('报价明细与原导入记录不一致，请刷新后重试')

        for item in items:
            if int(item['unit_price_minor']) < 0 or int(item['amount_minor']) < 0:
                raise ValueError('报价明细金额不能为负数')

        total_amount_minor = sum(int(item['amount_minor']) for item in items)
        if total_amount_minor < 0 or total_amount_minor > SQLITE_MAX_INTEGER:
            raise ValueError('报价总额超出可存储范围')
        before = {'quote': dict(row), 'items': list(stored_by_id.values())}
        conn.execute(
            """UPDATE supplier_quotes
               SET quote_date = ?, quote_valid_until = ?, total_amount_minor = ?,
                   tax_rate_bps = ?, price_basis = ?, delivery_period = ?,
                   payment_terms = ?, warranty_period = ?, package_transport = ?,
                   technical_deviation = ?, commercial_deviation = ?, updated_at = ?
               WHERE id = ?""",
            (
                header.get('quote_date') or '', header.get('quote_valid_until') or '',
                total_amount_minor, header.get('tax_rate_bps'), header['price_basis'],
                header.get('delivery_period') or '', header.get('payment_terms') or '',
                header.get('warranty_period') or '', header.get('package_transport') or '',
                header.get('technical_deviation') or '',
                header.get('commercial_deviation') or '', now, quote_id,
            ),
        )
        for item_id, item in submitted_by_id.items():
            conn.execute(
                """UPDATE supplier_quote_items
                   SET unit_price_minor = ?, amount_minor = ?, delivery_period = ?,
                       technical_deviation = ?, commercial_deviation = ?, remark = ?
                   WHERE id = ? AND quote_id = ?""",
                (
                    int(item['unit_price_minor']), int(item['amount_minor']),
                    item.get('delivery_period') or '',
                    item.get('technical_deviation') or '',
                    item.get('commercial_deviation') or '', item.get('remark') or '',
                    item_id, quote_id,
                ),
            )
        invalidated = _invalidate_comparisons(conn, row['project_id'])
        audit(
            conn, 'supplier_quote', quote_id, 'update', before=before,
            after={
                'header': {**header, 'total_amount_minor': total_amount_minor},
                'items': items,
                'invalidated_comparison_runs': invalidated,
            },
        )
        return row['project_id']


def delete_quote(get_conn, audit, now_func, quote_id):
    now = now_func()
    with get_conn() as conn:
        row = conn.execute(
            """SELECT q.*, f.relative_path AS original_relative_path
               FROM supplier_quotes q
               LEFT JOIN project_files f ON f.id = q.original_file_id
               WHERE q.id = ?""",
            (quote_id,),
        ).fetchone()
        if not row:
            raise ValueError('供应商报价不存在')
        if _quote_is_award_locked(conn, quote_id):
            raise ValueError('该报价已用于成交建议，不能删除')

        quote = dict(row)
        item_count = conn.execute(
            'SELECT COUNT(*) FROM supplier_quote_items WHERE quote_id = ?',
            (quote_id,),
        ).fetchone()[0]
        invalidated = _invalidate_comparisons(conn, quote['project_id'])
        conn.execute('DELETE FROM supplier_quotes WHERE id = ?', (quote_id,))

        file_deleted = False
        if quote.get('original_file_id'):
            file_still_used = conn.execute(
                'SELECT 1 FROM supplier_quotes WHERE original_file_id = ? LIMIT 1',
                (quote['original_file_id'],),
            ).fetchone()
            if not file_still_used:
                file_deleted = bool(conn.execute(
                    'DELETE FROM project_files WHERE id = ?',
                    (quote['original_file_id'],),
                ).rowcount)
        if quote.get('import_job_id'):
            conn.execute(
                """UPDATE quote_import_jobs
                   SET status = 'cancelled', confirmed_at = '' WHERE id = ?""",
                (quote['import_job_id'],),
            )
        conn.execute(
            """UPDATE quote_mapping_jobs SET status = 'cancelled', updated_at = ?
               WHERE project_id = ? AND supplier_id = ? AND quote_round = ?
                 AND relative_path = ?""",
            (
                now, quote['project_id'], quote['supplier_id'], quote['quote_round'],
                quote.get('original_relative_path') or '',
            ),
        )

        remaining_supplier_quotes = conn.execute(
            """SELECT 1 FROM supplier_quotes
               WHERE supplier_id = ? AND status = 'confirmed' LIMIT 1""",
            (quote['supplier_id'],),
        ).fetchone()
        conn.execute(
            'UPDATE project_suppliers SET quote_status = ?, updated_at = ? WHERE id = ?',
            ('received' if remaining_supplier_quotes else 'pending', now, quote['supplier_id']),
        )
        remaining_project_quotes = conn.execute(
            """SELECT 1 FROM supplier_quotes
               WHERE project_id = ? AND status = 'confirmed' LIMIT 1""",
            (quote['project_id'],),
        ).fetchone()
        if not remaining_project_quotes:
            conn.execute(
                """UPDATE procurement_projects
                   SET status = CASE WHEN status = 'quotes_received'
                                     THEN 'documents_ready' ELSE status END,
                       updated_at = ? WHERE id = ?""",
                (now, quote['project_id']),
            )
        audit(
            conn, 'supplier_quote', quote_id, 'delete', before=quote,
            after={
                'item_count': item_count,
                'invalidated_comparison_runs': invalidated,
                'original_file_removed': file_deleted,
            },
        )
        return {
            'project_id': quote['project_id'],
            'relative_path': quote.get('original_relative_path') if file_deleted else '',
        }
