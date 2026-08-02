"""Workbench todo aggregation for first-line operators."""

from __future__ import annotations

from datetime import date, timedelta

import ledger_store
import procurement_store


def _todo(kind, severity, title, subject, url, due_date='', amount=None, owner='', badge=''):
    return {
        'kind': kind,
        'severity': severity,
        'title': title,
        'subject': subject or '',
        'url': url,
        'due_date': due_date or '',
        'amount': amount,
        'owner': owner or '',
        'badge': badge or '',
    }


def _expired_contracts(today):
    today_str = today.strftime('%Y-%m-%d')
    with ledger_store.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM contracts
            WHERE expiry_date != '' AND expiry_date IS NOT NULL
              AND expiry_date < ?
              AND status IN ('signed', 'active')
              AND (deleted_at = '' OR deleted_at IS NULL)
            ORDER BY expiry_date
            LIMIT 20
            """,
            (today_str,),
        ).fetchall()
    return [ledger_store.row_to_dict(row) for row in rows]


def _payment_todos(today):
    today_str = today.strftime('%Y-%m-%d')
    tomorrow = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    due_soon_end = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    todos = []

    overdue_or_today = ledger_store.list_payment_plans(
        confirm_status='confirmed',
        payment_status='unpaid',
        end_date=today_str,
        page=0,
        limit=20,
    )
    for row in overdue_or_today[:20]:
        due_date = row.get('due_date') or ''
        is_overdue = bool(due_date and due_date < today_str)
        unpaid = (row.get('due_amount') or 0) - (row.get('paid_amount') or 0)
        todos.append(_todo(
            'payment',
            'high' if is_overdue else 'medium',
            '付款已逾期' if is_overdue else '今日应付',
            row.get('contract_title') or row.get('contract_no') or '未命名合同',
            f"/contracts/{row['contract_id']}",
            due_date=due_date,
            amount=unpaid,
            owner=row.get('owner') or '',
            badge=row.get('phase_name') or '付款',
        ))

    due_soon = ledger_store.list_payment_plans(
        confirm_status='confirmed',
        payment_status='unpaid',
        start_date=tomorrow,
        end_date=due_soon_end,
        page=0,
        limit=20,
    )
    for row in due_soon[:20]:
        unpaid = (row.get('due_amount') or 0) - (row.get('paid_amount') or 0)
        todos.append(_todo(
            'payment',
            'medium',
            '7 天内应付',
            row.get('contract_title') or row.get('contract_no') or '未命名合同',
            f"/contracts/{row['contract_id']}",
            due_date=row.get('due_date') or '',
            amount=unpaid,
            owner=row.get('owner') or '',
            badge=row.get('phase_name') or '付款',
        ))

    pending = ledger_store.list_payment_plans(confirm_status='pending', page=0, limit=20)
    for row in pending[:20]:
        todos.append(_todo(
            'payment',
            'medium',
            '付款计划待确认',
            row.get('contract_title') or row.get('contract_no') or '未命名合同',
            f"/contracts/{row['contract_id']}",
            due_date=row.get('due_date') or '',
            amount=row.get('due_amount'),
            owner=row.get('owner') or '',
            badge='待确认',
        ))
    return todos


def _contract_todos(today):
    todos = []
    for row in _expired_contracts(today):
        todos.append(_todo(
            'contract',
            'high',
            '合同已过期',
            row.get('title') or row.get('contract_no') or '未命名合同',
            f"/contracts/{row['id']}",
            due_date=row.get('expiry_date') or '',
            amount=row.get('amount'),
            owner=row.get('owner') or '',
            badge=row.get('contract_no') or '',
        ))
    for row in ledger_store.get_expiring_contracts(days=30, limit=20):
        todos.append(_todo(
            'contract',
            'medium',
            '合同 30 天内到期',
            row.get('title') or row.get('contract_no') or '未命名合同',
            f"/contracts/{row['id']}",
            due_date=row.get('expiry_date') or '',
            amount=row.get('amount'),
            owner=row.get('owner') or '',
            badge=row.get('contract_no') or '',
        ))
    return todos


def _procurement_todo_for_project(project):
    project_id = project['id']
    status = project.get('status') or ''
    item_count = project.get('item_count') or 0
    supplier_count = project.get('supplier_count') or 0
    quote_count = project.get('quote_count') or 0
    base_url = f"/procurement/projects/{project_id}"

    if status == 'archived':
        return None
    if item_count == 0:
        return _todo('procurement', 'medium', '采购明细待录入', project['project_name'], base_url + '#items',
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    if supplier_count == 0:
        return _todo('procurement', 'medium', '候选供应商待维护', project['project_name'], base_url + '#suppliers',
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    if quote_count == 0 and status in {'draft', 'documents_ready', 'inquiry_sent'}:
        return _todo('procurement', 'medium', '供应商报价待导入', project['project_name'],
                     f"/procurement/projects/{project_id}/quotes/import",
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    if status == 'quotes_received':
        return _todo('procurement', 'medium', '报价待横向比价', project['project_name'],
                     f"/procurement/projects/{project_id}/comparison",
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    if status == 'clarifying':
        return _todo('procurement', 'medium', '比价异常待澄清', project['project_name'], base_url + '#clarifications',
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    if status in {'negotiating', 'award_draft'}:
        return _todo('procurement', 'medium', '成交建议待确认', project['project_name'],
                     f"/procurement/projects/{project_id}/award",
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    if status in {'award_confirmed', 'contract_draft'}:
        return _todo('procurement', 'medium', '成交结果待转合同', project['project_name'],
                     f"/procurement/projects/{project_id}/to-contract",
                     owner=project.get('owner') or '', badge=project.get('project_no') or '')
    return None


def _procurement_todos():
    result = procurement_store.list_projects(page=1, per_page=100)
    todos = []
    for project in result.get('rows', []):
        todo = _procurement_todo_for_project(project)
        if todo:
            todos.append(todo)
    return todos


def build_workbench(limit=12, today=None):
    today = today or date.today()
    todos = _payment_todos(today) + _contract_todos(today) + _procurement_todos()
    severity_order = {'high': 0, 'medium': 1, 'normal': 2, 'low': 3}
    todos.sort(key=lambda item: (
        severity_order.get(item['severity'], 9),
        item.get('due_date') or '9999-12-31',
        item.get('title') or '',
    ))
    summary = {
        'total': len(todos),
        'high': sum(1 for item in todos if item['severity'] == 'high'),
        'medium': sum(1 for item in todos if item['severity'] == 'medium'),
        'payment': sum(1 for item in todos if item['kind'] == 'payment'),
        'contract': sum(1 for item in todos if item['kind'] == 'contract'),
        'procurement': sum(1 for item in todos if item['kind'] == 'procurement'),
    }
    return {'items': todos[:limit], 'summary': summary}
