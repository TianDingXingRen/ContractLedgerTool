"""Award recommendation and contract-link persistence helpers."""

import json


def create_award_recommendation(
    get_conn, audit, now_func, project_id, supplier_id, quote_id, data, items
):
    now = now_func()
    with get_conn() as conn:
        version = conn.execute(
            'SELECT COALESCE(MAX(version), 0) + 1 FROM award_recommendations WHERE project_id = ?',
            (project_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO award_recommendations
               (project_id, version, supplier_id, quote_id, recommended_amount_minor, currency,
                reason_summary, price_reason, technical_reason, commercial_reason, delivery_reason,
                risk_note, lowest_price_not_selected_reason, contract_notice, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?)""",
            (project_id, version, supplier_id, quote_id, int(data['recommended_amount_minor']),
             data.get('currency') or 'CNY', data['reason_summary'], data.get('price_reason') or '',
             data.get('technical_reason') or '', data.get('commercial_reason') or '',
             data.get('delivery_reason') or '', data.get('risk_note') or '',
             data.get('lowest_price_not_selected_reason') or '',
             data.get('contract_notice') or '', now, now),
        )
        recommendation_id = cur.lastrowid
        for item in items:
            conn.execute(
                """INSERT INTO award_recommendation_items
                   (recommendation_id, project_item_id, quote_item_id, supplier_id, quote_id, item_name, spec_model,
                    quantity_text, unit, unit_price_minor, amount_minor, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (recommendation_id, item['project_item_id'], item['id'], supplier_id,
                 quote_id, item['item_name'], item.get('spec_model') or '',
                 item['quantity_text'], item['unit'], item['unit_price_minor'],
                 item['amount_minor'], now),
            )
        conn.execute(
            "UPDATE award_recommendations SET status = 'superseded' WHERE project_id = ? AND id != ? AND status = 'confirmed'",
            (project_id, recommendation_id),
        )
        conn.execute(
            "UPDATE procurement_projects SET status = 'award_confirmed', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        audit(conn, 'award_recommendation', recommendation_id, 'confirm', after=data)
        return recommendation_id


def create_split_award_recommendation(get_conn, audit, now_func, project_id, data, selections):
    now = now_func()
    primary = selections[0]
    supplier_names = list(dict.fromkeys(item['supplier_name'] for item in selections))
    with get_conn() as conn:
        version = conn.execute(
            'SELECT COALESCE(MAX(version), 0) + 1 FROM award_recommendations WHERE project_id = ?',
            (project_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """INSERT INTO award_recommendations
               (project_id, version, supplier_id, quote_id, recommended_amount_minor, currency,
                reason_summary, price_reason, technical_reason, commercial_reason, delivery_reason,
                risk_note, lowest_price_not_selected_reason, contract_notice, is_split,
                supplier_summary, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'CNY', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'confirmed', ?, ?)""",
            (project_id, version, primary['supplier_id'], primary['quote_id'],
             sum(item['amount_minor'] for item in selections), data['reason_summary'],
             data.get('price_reason') or '', data.get('technical_reason') or '',
             data.get('commercial_reason') or '', data.get('delivery_reason') or '',
             data.get('risk_note') or '', data.get('lowest_price_not_selected_reason') or '',
             data.get('contract_notice') or '', '、'.join(supplier_names), now, now),
        )
        recommendation_id = cur.lastrowid
        for item in selections:
            conn.execute(
                """INSERT INTO award_recommendation_items
                   (recommendation_id, project_item_id, quote_item_id, supplier_id, quote_id,
                    item_name, spec_model, quantity_text, unit, unit_price_minor, amount_minor, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (recommendation_id, item['project_item_id'], item['id'], item['supplier_id'],
                 item['quote_id'], item['item_name'], item.get('spec_model') or '',
                 item['quantity_text'], item['unit'], item['unit_price_minor'],
                 item['amount_minor'], now),
            )
        conn.execute(
            "UPDATE award_recommendations SET status = 'superseded' WHERE project_id = ? AND id != ? AND status = 'confirmed'",
            (project_id, recommendation_id),
        )
        conn.execute(
            "UPDATE procurement_projects SET status = 'award_confirmed', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        audit(
            conn, 'award_recommendation', recommendation_id, 'confirm_split',
            after={'supplier_names': supplier_names, 'item_count': len(selections)},
        )
        return recommendation_id


def get_latest_award(get_conn, project_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT a.*, s.supplier_name, q.delivery_period, q.payment_terms,
                      q.warranty_period, q.technical_deviation, q.commercial_deviation
               FROM award_recommendations a
               JOIN project_suppliers s ON s.id = a.supplier_id
               JOIN supplier_quotes q ON q.id = a.quote_id
               WHERE a.project_id = ? AND a.status IN ('confirmed','converted')
               ORDER BY a.version DESC LIMIT 1""", (project_id,),
        ).fetchone()
        if not row:
            return None
        items = conn.execute(
            """SELECT ai.*, s.supplier_name
               FROM award_recommendation_items ai
               LEFT JOIN project_suppliers s ON s.id = ai.supplier_id
               WHERE ai.recommendation_id = ? ORDER BY ai.id""", (row['id'],),
        ).fetchall()
    result = dict(row)
    result['items'] = [dict(item) for item in items]
    return result


def get_or_create_contract_data_sheet(
    get_conn, row_to_dict, now_func, project_id, recommendation_id, payload
):
    now = now_func()
    with get_conn() as conn:
        existing = conn.execute(
            'SELECT * FROM contract_data_sheets WHERE recommendation_id = ?',
            (recommendation_id,),
        ).fetchone()
        if existing:
            return dict(existing)
        cur = conn.execute(
            """INSERT INTO contract_data_sheets
               (project_id, recommendation_id, schema_version, payload_json, status, created_at, updated_at)
               VALUES (?, ?, '1.0', ?, 'draft', ?, ?)""",
            (project_id, recommendation_id, json.dumps(payload, ensure_ascii=False), now, now),
        )
        sheet_id = cur.lastrowid
        conn.execute(
            "UPDATE procurement_projects SET status = 'contract_draft', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        return row_to_dict(
            conn.execute('SELECT * FROM contract_data_sheets WHERE id = ?', (sheet_id,)).fetchone()
        )


def get_contract_data_sheet(get_conn, row_to_dict, sheet_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM contract_data_sheets WHERE id = ?', (sheet_id,)
        ).fetchone()
    result = row_to_dict(row)
    if result:
        result['payload'] = json.loads(result['payload_json'])
    return result


def mark_data_sheet_in_editor(get_conn, now_func, sheet_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE contract_data_sheets SET status = 'in_editor', updated_at = ? WHERE id = ?",
            (now_func(), sheet_id),
        )


def complete_contract_link(get_conn, audit, now_func, sheet_id, contract_id):
    now = now_func()
    with get_conn() as conn:
        sheet = conn.execute(
            'SELECT * FROM contract_data_sheets WHERE id = ?', (sheet_id,)
        ).fetchone()
        if not sheet:
            raise ValueError('合同数据单不存在')
        existing = conn.execute(
            'SELECT * FROM project_contract_links WHERE data_sheet_id = ?', (sheet_id,)
        ).fetchone()
        if existing:
            if existing['contract_id'] != contract_id:
                raise ValueError('该合同数据单已关联其他合同')
            conn.execute(
                """INSERT OR IGNORE INTO procurement_contract_refs
                   (project_id, contract_id, source_type, source_id, created_at)
                   VALUES (?, ?, 'award', ?, ?)""",
                (sheet['project_id'], contract_id, sheet['recommendation_id'], now),
            )
            return existing['id']
        cur = conn.execute(
            """INSERT INTO project_contract_links
               (project_id, recommendation_id, data_sheet_id, contract_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (sheet['project_id'], sheet['recommendation_id'], sheet_id, contract_id, now),
        )
        conn.execute(
            "UPDATE contract_data_sheets SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, sheet_id),
        )
        conn.execute(
            "UPDATE award_recommendations SET status = 'converted', updated_at = ? WHERE id = ?",
            (now, sheet['recommendation_id']),
        )
        conn.execute(
            "UPDATE procurement_projects SET status = 'contract_created', updated_at = ? WHERE id = ?",
            (now, sheet['project_id']),
        )
        conn.execute(
            """INSERT OR IGNORE INTO procurement_contract_refs
               (project_id, contract_id, source_type, source_id, created_at)
               VALUES (?, ?, 'award', ?, ?)""",
            (sheet['project_id'], contract_id, sheet['recommendation_id'], now),
        )
        audit(
            conn, 'contract_data_sheet', sheet_id, 'complete_contract_link',
            after={'contract_id': contract_id},
        )
        return cur.lastrowid


def add_contract_ref(
    get_conn, audit, now_func, project_id, contract_id, source_type='direct_contract',
    source_id=None,
):
    now = now_func()
    with get_conn() as conn:
        project = conn.execute(
            'SELECT * FROM procurement_projects WHERE id = ?', (project_id,)
        ).fetchone()
        if not project:
            raise ValueError('采购项目不存在')
        contract = conn.execute('SELECT id FROM contracts WHERE id = ?', (contract_id,)).fetchone()
        if not contract:
            raise ValueError('合同不存在')
        conn.execute(
            """INSERT OR IGNORE INTO procurement_contract_refs
               (project_id, contract_id, source_type, source_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, contract_id, source_type or 'direct_contract', source_id, now),
        )
        conn.execute(
            "UPDATE procurement_projects SET status = 'contract_created', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        audit(
            conn, 'project', project_id, 'contract_ref_create',
            after={'contract_id': contract_id, 'source_type': source_type, 'source_id': source_id},
        )


def get_project_contract_links(get_conn, project_id):
    with get_conn() as conn:
        linked = conn.execute(
            """SELECT l.*, c.contract_no, c.title, c.docx_path
               FROM project_contract_links l JOIN contracts c ON c.id = l.contract_id
               WHERE l.project_id = ? ORDER BY l.id DESC""", (project_id,),
        ).fetchall()
        refs = conn.execute(
            """SELECT r.*, c.contract_no, c.title, c.docx_path
               FROM procurement_contract_refs r JOIN contracts c ON c.id = r.contract_id
               WHERE r.project_id = ? ORDER BY r.id DESC""", (project_id,),
        ).fetchall()
    result = []
    seen = set()
    for row in refs:
        item = dict(row)
        item.setdefault('source_type', 'direct_contract')
        result.append(item)
        seen.add(item['contract_id'])
    for row in linked:
        item = dict(row)
        if item['contract_id'] in seen:
            continue
        item['source_type'] = 'award'
        item['source_id'] = item.get('recommendation_id')
        result.append(item)
        seen.add(item['contract_id'])
    return result


def contract_has_refs(get_conn, contract_id):
    with get_conn() as conn:
        return bool(conn.execute(
            """SELECT 1 FROM project_contract_links WHERE contract_id = ?
               UNION ALL
               SELECT 1 FROM procurement_contract_refs WHERE contract_id = ?
               LIMIT 1""",
            (contract_id, contract_id),
        ).fetchone())
