"""SQLite persistence for the procurement pre-workbench.

The procurement module shares the existing application database and connection
factory, while keeping its SQL and domain operations separate from the contract
ledger store.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import ledger_store
from . import award_contracts
from . import comparison_workflow
from . import project_components
from . import project_queries
from . import quote_jobs
from .schema import (
    PROCUREMENT_SCHEMA_SQL,
    SCHEMA_VERSION_INSERT_SQL,
    V2_COLUMN_MIGRATIONS,
    V3_CONTRACT_REFS_INDEX_SQL,
    V3_CONTRACT_REFS_SQL,
)


PROJECT_STATUSES = {
    'draft', 'documents_ready', 'inquiry_sent', 'quotes_received',
    'clarifying', 'negotiating', 'award_draft', 'award_confirmed',
    'contract_draft', 'contract_created', 'archived',
}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _dict(row):
    return dict(row) if row is not None else None


def _normalize_name(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def _audit(conn, entity_type, entity_id, action, before=None, after=None, note=''):
    conn.execute(
        """INSERT INTO procurement_audit_events
           (entity_type, entity_id, action, before_json, after_json, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            entity_type, int(entity_id), action,
            json.dumps(before, ensure_ascii=False) if before is not None else '',
            json.dumps(after, ensure_ascii=False) if after is not None else '',
            str(note or ''), _now(),
        ),
    )


def _ensure_column(conn, table_name, column_name, column_sql):
    columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table_name})').fetchall()}
    if column_name not in columns:
        conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}')


def init_db():
    """Create the procurement schema idempotently."""
    with ledger_store.get_conn() as conn:
        now = _now()
        conn.executescript(PROCUREMENT_SCHEMA_SQL)
        conn.execute(SCHEMA_VERSION_INSERT_SQL, (1, now))
        for table_name, column_name, column_sql in V2_COLUMN_MIGRATIONS:
            _ensure_column(conn, table_name, column_name, column_sql)
        conn.execute(SCHEMA_VERSION_INSERT_SQL, (2, now))
        conn.execute(V3_CONTRACT_REFS_SQL)
        conn.execute(V3_CONTRACT_REFS_INDEX_SQL)
        conn.execute(SCHEMA_VERSION_INSERT_SQL, (3, now))


def create_project(data):
    now = _now()
    with ledger_store.get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO procurement_projects
               (project_no, project_name, purchase_method, demand_department, owner,
                budget_minor, target_price_minor, currency, delivery_place,
                delivery_requirement, payment_requirement, status, remark,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)""",
            (
                data['project_no'], data['project_name'], data.get('purchase_method') or 'competitive_negotiation',
                data.get('demand_department') or '', data.get('owner') or '', data.get('budget_minor'),
                data.get('target_price_minor'), data.get('currency') or 'CNY', data.get('delivery_place') or '',
                data.get('delivery_requirement') or '', data.get('payment_requirement') or '',
                data.get('remark') or '', now, now,
            ),
        )
        project_id = cur.lastrowid
        _audit(conn, 'project', project_id, 'create', after=data)
        return project_id


def update_project(project_id, data):
    allowed = {
        'project_name', 'purchase_method', 'demand_department', 'owner',
        'budget_minor', 'target_price_minor', 'currency', 'delivery_place',
        'delivery_requirement', 'payment_requirement', 'remark',
    }
    changes = {key: data[key] for key in allowed if key in data}
    if not changes:
        return get_project(project_id)
    with ledger_store.get_conn() as conn:
        before = _dict(conn.execute('SELECT * FROM procurement_projects WHERE id = ?', (project_id,)).fetchone())
        if not before:
            raise ValueError('采购项目不存在')
        assignments = ', '.join(f'{key} = ?' for key in changes)
        conn.execute(
            f'UPDATE procurement_projects SET {assignments}, updated_at = ? WHERE id = ?',
            (*changes.values(), _now(), project_id),
        )
        after = _dict(conn.execute('SELECT * FROM procurement_projects WHERE id = ?', (project_id,)).fetchone())
        _audit(conn, 'project', project_id, 'update', before=before, after=after)
        return after


def get_project(project_id):
    return project_queries.get_project(ledger_store.get_conn, _dict, project_id)


def list_projects(status='', q='', page=1, per_page=20):
    return project_queries.list_projects(
        ledger_store.get_conn, _dict, status=status, q=q, page=page, per_page=per_page
    )


def transition_project_status(project_id, new_status, note=''):
    if new_status not in PROJECT_STATUSES:
        raise ValueError('采购项目状态无效')
    with ledger_store.get_conn() as conn:
        row = conn.execute('SELECT * FROM procurement_projects WHERE id = ?', (project_id,)).fetchone()
        if not row:
            raise ValueError('采购项目不存在')
        before = dict(row)
        archived_at = _now() if new_status == 'archived' else (before.get('archived_at') or '')
        conn.execute(
            'UPDATE procurement_projects SET status = ?, archived_at = ?, updated_at = ? WHERE id = ?',
            (new_status, archived_at, _now(), project_id),
        )
        _audit(conn, 'project', project_id, 'status_change', before={'status': before['status']},
               after={'status': new_status}, note=note)


def record_workflow_jump(project_id, target_stage, skipped_stages=None, note='', before_status='', after_status=''):
    skipped_stages = skipped_stages or []
    with ledger_store.get_conn() as conn:
        row = conn.execute('SELECT id FROM procurement_projects WHERE id = ?', (project_id,)).fetchone()
        if not row:
            raise ValueError('采购项目不存在')
        _audit(
            conn, 'project', project_id, 'workflow_jump',
            before={'status': before_status} if before_status else None,
            after={
                'target_stage': target_stage,
                'skipped_stages': skipped_stages,
                'status': after_status,
            },
            note=note,
        )


def list_project_audit_events(project_id, actions=None):
    return project_queries.list_project_audit_events(
        ledger_store.get_conn, project_id, actions=actions
    )


def list_project_items(project_id):
    return project_components.list_project_items(ledger_store.get_conn, project_id)


def add_project_item(project_id, data):
    return project_components.add_project_item(
        ledger_store.get_conn, _audit, _now, project_id, data
    )


def add_project_items_bulk(project_id, items):
    return project_components.add_project_items_bulk(
        ledger_store.get_conn, _audit, _now, project_id, items
    )


def get_project_item(item_id):
    return project_components.get_project_item(ledger_store.get_conn, _dict, item_id)


def update_project_item(project_id, item_id, data):
    return project_components.update_project_item(
        ledger_store.get_conn, _audit, _now, project_id, item_id, data
    )


def delete_project_item(project_id, item_id):
    return project_components.delete_project_item(
        ledger_store.get_conn, _audit, project_id, item_id
    )


def list_project_suppliers(project_id):
    return project_components.list_project_suppliers(ledger_store.get_conn, project_id)


def get_project_supplier(supplier_id):
    return project_components.get_project_supplier(
        ledger_store.get_conn, _dict, supplier_id
    )


def update_project_supplier(project_id, supplier_id, data):
    return project_components.update_project_supplier(
        ledger_store.get_conn, _audit, _now, _normalize_name,
        project_id, supplier_id, data
    )


def add_project_supplier(project_id, data):
    return project_components.add_project_supplier(
        ledger_store.get_conn, _audit, _now, _normalize_name, project_id, data
    )


def delete_project_supplier(project_id, supplier_id):
    return project_components.delete_project_supplier(
        ledger_store.get_conn, _audit, project_id, supplier_id
    )


def register_project_file(project_id, file_type, relative_path, original_name='', sha256='', size_bytes=0):
    return project_components.register_project_file(
        ledger_store.get_conn, _now, project_id, file_type, relative_path,
        original_name=original_name, sha256=sha256, size_bytes=size_bytes,
    )


def list_project_files(project_id):
    return project_components.list_project_files(ledger_store.get_conn, project_id)


def get_project_file(file_id):
    return project_components.get_project_file(ledger_store.get_conn, _dict, file_id)


def create_import_job(data):
    return quote_jobs.create_import_job(ledger_store.get_conn, _now, data)


def get_import_job(job_id):
    return quote_jobs.get_import_job(ledger_store.get_conn, _dict, job_id)


def create_mapping_job(data):
    return quote_jobs.create_mapping_job(ledger_store.get_conn, _now, data)


def get_mapping_job(job_id):
    return quote_jobs.get_mapping_job(ledger_store.get_conn, _dict, job_id)


def update_mapping_job(job_id, column_map, metadata, status='parsed'):
    return quote_jobs.update_mapping_job(
        ledger_store.get_conn, _now, job_id, column_map, metadata, status
    )


def mark_mapping_job_confirmed(job_id):
    return quote_jobs.mark_mapping_job_confirmed(ledger_store.get_conn, _now, job_id)


def confirm_import_job(job_id):
    return quote_jobs.confirm_import_job(ledger_store.get_conn, _audit, _now, job_id)


def list_quotes(project_id):
    return quote_jobs.list_quotes(ledger_store.get_conn, project_id)


def get_latest_quotes(project_id):
    return quote_jobs.get_latest_quotes(ledger_store.get_conn, project_id)


def get_quote(quote_id):
    return quote_jobs.get_quote(ledger_store.get_conn, _dict, quote_id)


def get_quote_items(quote_id):
    return quote_jobs.get_quote_items(ledger_store.get_conn, quote_id)


def create_comparison_run(project_id, quote_ids, rule_config, results):
    return comparison_workflow.create_comparison_run(
        ledger_store.get_conn, _audit, _now, project_id, quote_ids, rule_config, results
    )


def get_latest_comparison(project_id):
    return comparison_workflow.get_latest_comparison(ledger_store.get_conn, project_id)


def create_clarifications_from_results(project_id, questions):
    return comparison_workflow.create_clarifications_from_results(
        ledger_store.get_conn, _now, project_id, questions
    )


def list_clarifications(project_id):
    return comparison_workflow.list_clarifications(ledger_store.get_conn, project_id)


def update_clarification(question_id, data):
    return comparison_workflow.update_clarification(
        ledger_store.get_conn, _audit, _now, question_id, data
    )


def save_negotiation_round(project_id, round_no, meeting_date, summary, commitments):
    now = _now()
    with ledger_store.get_conn() as conn:
        row = conn.execute(
            'SELECT id FROM negotiation_rounds WHERE project_id = ? AND round_no = ?',
            (project_id, round_no),
        ).fetchone()
        if row:
            round_id = row[0]
            conn.execute(
                "UPDATE negotiation_rounds SET meeting_date = ?, summary = ?, updated_at = ? WHERE id = ?",
                (meeting_date, summary, now, round_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO negotiation_rounds
                   (project_id, round_no, meeting_date, summary, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, round_no, meeting_date, summary, now, now),
            )
            round_id = cur.lastrowid
        for item in commitments:
            conn.execute(
                """INSERT INTO negotiation_commitments
                   (round_id, supplier_id, quote_id, quote_amount_minor, delivery_period,
                    payment_terms, commitment, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(round_id, supplier_id) DO UPDATE SET
                     quote_id=excluded.quote_id, quote_amount_minor=excluded.quote_amount_minor,
                     delivery_period=excluded.delivery_period, payment_terms=excluded.payment_terms,
                     commitment=excluded.commitment, updated_at=excluded.updated_at""",
                (round_id, item['supplier_id'], item.get('quote_id'), item.get('quote_amount_minor'),
                 item.get('delivery_period') or '', item.get('payment_terms') or '',
                 item.get('commitment') or '', now, now),
            )
        conn.execute(
            "UPDATE procurement_projects SET status = 'negotiating', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        _audit(conn, 'negotiation_round', round_id, 'save', after={'round_no': round_no})
        return round_id


def list_negotiation_rounds(project_id):
    with ledger_store.get_conn() as conn:
        rounds = conn.execute(
            'SELECT * FROM negotiation_rounds WHERE project_id = ? ORDER BY round_no', (project_id,)
        ).fetchall()
        result = []
        for round_row in rounds:
            item = dict(round_row)
            commitments = conn.execute(
                """SELECT c.*, s.supplier_name
                   FROM negotiation_commitments c JOIN project_suppliers s ON s.id = c.supplier_id
                   WHERE c.round_id = ? ORDER BY s.supplier_name""", (round_row['id'],),
            ).fetchall()
            item['commitments'] = [dict(row) for row in commitments]
            result.append(item)
    return result


def get_rule_config(project_id):
    return comparison_workflow.get_rule_config(ledger_store.get_conn, _dict, project_id)


def save_rule_config(project_id, data):
    return comparison_workflow.save_rule_config(
        ledger_store.get_conn, _now, project_id, data
    )


def create_award_recommendation(project_id, supplier_id, quote_id, data, items):
    return award_contracts.create_award_recommendation(
        ledger_store.get_conn, _audit, _now, project_id, supplier_id, quote_id, data, items
    )


def create_split_award_recommendation(project_id, data, selections):
    return award_contracts.create_split_award_recommendation(
        ledger_store.get_conn, _audit, _now, project_id, data, selections
    )


def get_latest_award(project_id):
    return award_contracts.get_latest_award(ledger_store.get_conn, project_id)


def get_or_create_contract_data_sheet(project_id, recommendation_id, payload):
    return award_contracts.get_or_create_contract_data_sheet(
        ledger_store.get_conn, _dict, _now, project_id, recommendation_id, payload
    )


def get_contract_data_sheet(sheet_id):
    return award_contracts.get_contract_data_sheet(ledger_store.get_conn, _dict, sheet_id)


def mark_data_sheet_in_editor(sheet_id):
    return award_contracts.mark_data_sheet_in_editor(ledger_store.get_conn, _now, sheet_id)


def complete_contract_link(sheet_id, contract_id):
    return award_contracts.complete_contract_link(
        ledger_store.get_conn, _audit, _now, sheet_id, contract_id
    )


def add_contract_ref(project_id, contract_id, source_type='direct_contract', source_id=None):
    return award_contracts.add_contract_ref(
        ledger_store.get_conn, _audit, _now, project_id, contract_id,
        source_type=source_type, source_id=source_id,
    )


def get_project_contract_links(project_id):
    return award_contracts.get_project_contract_links(ledger_store.get_conn, project_id)


def contract_has_refs(contract_id):
    return award_contracts.contract_has_refs(ledger_store.get_conn, contract_id)
