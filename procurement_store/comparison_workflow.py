"""Comparison, clarification, and rule-config persistence helpers."""

import json


def create_comparison_run(get_conn, audit, now_func, project_id, quote_ids, rule_config, results):
    now = now_func()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO comparison_runs(project_id, quote_ids_json, rule_config_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (project_id, json.dumps(quote_ids), json.dumps(rule_config, ensure_ascii=False), now),
        )
        run_id = cur.lastrowid
        for result in results:
            conn.execute(
                """INSERT INTO comparison_results
                   (comparison_run_id, project_id, project_item_id, supplier_id, quote_id,
                    result_type, description, severity, suggestion, status, metric_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (run_id, project_id, result.get('project_item_id'), result.get('supplier_id'),
                 result.get('quote_id'), result['result_type'], result['description'],
                 result.get('severity') or 'medium', result.get('suggestion') or '',
                 json.dumps(result.get('metric') or {}, ensure_ascii=False), now),
            )
        audit(
            conn, 'comparison_run', run_id, 'create',
            after={'quote_ids': quote_ids, 'result_count': len(results)},
        )
        return run_id


def get_latest_comparison(get_conn, project_id):
    with get_conn() as conn:
        run = conn.execute(
            'SELECT * FROM comparison_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1',
            (project_id,),
        ).fetchone()
        if not run:
            return None
        results = conn.execute(
            """SELECT r.*, s.supplier_name, i.item_name
               FROM comparison_results r
               LEFT JOIN project_suppliers s ON s.id = r.supplier_id
               LEFT JOIN project_items i ON i.id = r.project_item_id
               WHERE r.comparison_run_id = ? ORDER BY r.id""", (run['id'],),
        ).fetchall()
    result = dict(run)
    result['quote_ids'] = json.loads(result['quote_ids_json'])
    result['rule_config'] = json.loads(result['rule_config_json'])
    result['results'] = [dict(row) for row in results]
    return result


def create_clarifications_from_results(get_conn, now_func, project_id, questions):
    now = now_func()
    created = 0
    with get_conn() as conn:
        for question in questions:
            cur = conn.execute(
                """INSERT OR IGNORE INTO clarification_questions
                   (project_id, supplier_id, project_item_id, question_type, question_text,
                    source_result_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (project_id, question.get('supplier_id'), question.get('project_item_id'),
                 question['question_type'], question['question_text'],
                 question.get('source_result_id'), now, now),
            )
            created += cur.rowcount
        if created:
            conn.execute(
                "UPDATE procurement_projects SET status = 'clarifying', updated_at = ? WHERE id = ?",
                (now, project_id),
            )
    return created


def list_clarifications(get_conn, project_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, s.supplier_name, i.item_name
               FROM clarification_questions c
               LEFT JOIN project_suppliers s ON s.id = c.supplier_id
               LEFT JOIN project_items i ON i.id = c.project_item_id
               WHERE c.project_id = ? ORDER BY c.updated_at DESC, c.id DESC""",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_clarification(get_conn, audit, now_func, question_id, data):
    allowed_statuses = {'pending', 'confirmed', 'sent', 'replied', 'closed'}
    status = data.get('status')
    if status not in allowed_statuses:
        raise ValueError('澄清问题状态无效')
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM clarification_questions WHERE id = ?', (question_id,)
        ).fetchone()
        if not row:
            raise ValueError('澄清问题不存在')
        conn.execute(
            """UPDATE clarification_questions
               SET question_text = ?, answer_text = ?, status = ?, updated_at = ? WHERE id = ?""",
            (data.get('question_text') or row['question_text'], data.get('answer_text') or '',
             status, now_func(), question_id),
        )
        audit(conn, 'clarification', question_id, 'update', before=dict(row), after=data)


def get_rule_config(get_conn, row_to_dict, project_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM procurement_rule_configs WHERE project_id = ?', (project_id,)
        ).fetchone()
    return row_to_dict(row) or {
        'project_id': project_id, 'price_threshold_percent': '20',
        'min_valid_suppliers': 2, 'require_same_price_basis': 1,
    }


def save_rule_config(get_conn, now_func, project_id, data):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO procurement_rule_configs
               (project_id, price_threshold_percent, min_valid_suppliers,
                require_same_price_basis, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                 price_threshold_percent=excluded.price_threshold_percent,
                 min_valid_suppliers=excluded.min_valid_suppliers,
                 require_same_price_basis=excluded.require_same_price_basis,
                 updated_at=excluded.updated_at""",
            (project_id, str(data['price_threshold_percent']), int(data['min_valid_suppliers']),
             1 if data.get('require_same_price_basis') else 0, now_func()),
        )
