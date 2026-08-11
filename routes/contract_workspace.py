"""Read-only contract workspace route and tab-specific view models."""

from datetime import date

from flask import render_template, request

import ledger_store
from routes.workspace_navigation import normalize_contract_tab


def _positive_page(name):
    try:
        return max(1, int(request.args.get(name, 1)))
    except (TypeError, ValueError):
        return 1


def _contract_activity(contract, notices, invoices, plans, history, limit=8):
    activity = []
    if contract.get('created_at'):
        activity.append({
            'title': '合同已导入' if contract.get('record_origin') == 'imported' else '合同已生成',
            'note': contract.get('contract_no') or contract.get('title') or '合同记录',
            'time': contract.get('created_at'),
            'tone': 'blue',
        })
    notice_labels = {
        'draft': '投产通知草稿已建立', 'issued': '投产通知已发出',
        'acknowledged': '供应商已确认投产通知', 'closed': '投产通知已关闭',
        'cancelled': '投产通知已取消',
    }
    for notice in notices:
        timestamp = (
            notice.get('closed_at') or notice.get('acknowledged_at') or
            notice.get('issued_at') or notice.get('created_at')
        )
        if timestamp:
            activity.append({
                'title': notice_labels.get(notice.get('status'), '投产通知已更新'),
                'note': f"{notice.get('notice_no') or '未编号'} · {notice.get('total_qty') or 0} 件",
                'time': timestamp,
                'tone': 'green' if notice.get('status') == 'closed' else 'blue',
            })
    for invoice in invoices:
        if invoice.get('created_at'):
            activity.append({
                'title': '发票已登记',
                'note': f"{invoice.get('invoice_no') or '未编号'} · {invoice.get('seller_name') or '未填写销方'}",
                'time': invoice.get('created_at'),
                'tone': 'green' if invoice.get('review_status') == 'verified' else 'orange',
            })
    for plan in plans:
        timestamp = plan.get('paid_date') or plan.get('created_at')
        if timestamp:
            activity.append({
                'title': '已登记付款' if plan.get('paid_amount') else '付款计划已形成',
                'note': plan.get('phase_name') or '付款计划',
                'time': timestamp,
                'tone': 'green' if plan.get('paid_amount') else 'blue',
            })
    for item in history:
        if item.get('changed_at'):
            activity.append({
                'title': '合同台账已修改',
                'note': f"{item.get('field') or '字段'}：{item.get('new_value') or '(空)'}",
                'time': item.get('changed_at'),
                'tone': 'gray',
            })
    return sorted(activity, key=lambda item: item['time'], reverse=True)[:limit]


def _empty_result():
    return {'rows': [], 'total': 0, 'page': 1, 'pages': 1}


def _history_page(contract_id):
    all_history = ledger_store.get_contract_history(contract_id)
    page = _positive_page('history_page')
    per_page = 20
    total = len(all_history)
    pages = (total + per_page - 1) // per_page or 1
    page = min(page, pages)
    return {
        'rows': all_history[(page - 1) * per_page:page * per_page],
        'total': total, 'page': page, 'pages': pages,
    }


def register_contract_workspace(bp):
    @bp.route('/contracts/<int:contract_id>')
    def contract_detail(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        import procurement_store

        tab = normalize_contract_tab(request.args.get('tab'))
        plans, payment_rules, payment_events = [], [], []
        contract_serials, active_contract_serials = [], []
        contract_items, production_notices, invoices, history, activity = [], [], [], [], []
        plan_result = _empty_result()
        notice_result = _empty_result()
        invoice_result = _empty_result()
        history_result = _empty_result()

        if tab == 'overview':
            contract_items = ledger_store.list_contract_items(contract_id)
            recent_notices = ledger_store.list_production_notices(
                contract_id=contract_id, page=1, per_page=6
            )['rows']
            recent_invoices = ledger_store.list_invoices(
                contract_id=contract_id, page=1, per_page=6
            )['rows']
            recent_plans = ledger_store.list_payment_plans(
                contract_id=contract_id, limit=8, include_void_contracts=True
            )
            recent_history = ledger_store.get_contract_history(contract_id)[:6]
            activity = _contract_activity(
                contract, recent_notices, recent_invoices, recent_plans, recent_history
            )
        elif tab == 'payments':
            contract_serials = ledger_store.list_contract_serials(
                contract_id, include_inactive=True
            )
            active_contract_serials = [
                row for row in contract_serials if row.get('status') == 'active'
            ]
            plan_result = ledger_store.list_payment_plans(
                contract_id=contract_id, page=_positive_page('plan_page'), per_page=20,
                include_void_contracts=True,
            )
            plans = plan_result['rows']
            today_text = date.today().strftime('%Y-%m-%d')
            for plan in plans:
                plan['unpaid_amount'] = max(
                    (plan.get('due_amount') or 0) - (plan.get('paid_amount') or 0), 0
                )
                plan['is_overdue'] = bool(
                    plan.get('due_date') and plan['due_date'] < today_text and
                    plan.get('payment_status') != 'paid'
                )
            payment_rules = ledger_store.list_payment_rules(contract_id)
            payment_events = ledger_store.list_payment_trigger_events(contract_id)
        elif tab == 'production':
            contract_items = ledger_store.list_contract_items(contract_id)
            notice_result = ledger_store.list_production_notices(
                contract_id=contract_id, page=_positive_page('notice_page'), per_page=20
            )
            production_notices = notice_result['rows']
        elif tab == 'invoices':
            invoice_result = ledger_store.list_invoices(
                contract_id=contract_id, page=_positive_page('invoice_page'), per_page=20
            )
            invoices = invoice_result['rows']
        elif tab == 'history':
            history_result = _history_page(contract_id)
            history = history_result['rows']

        return render_template(
            'contract_detail.html', contract=contract, tab=tab,
            summary=ledger_store.get_contract_workspace_summary(contract_id),
            plans=plans, plan_result=plan_result,
            payment_rules=payment_rules, payment_events=payment_events,
            contract_serials=contract_serials,
            active_contract_serials=active_contract_serials,
            contract_items=contract_items,
            production_notices=production_notices, notice_result=notice_result,
            invoices=invoices, invoice_result=invoice_result,
            history=history, history_result=history_result, activity=activity,
            today_str=date.today().strftime('%Y-%m-%d'),
            project_names=ledger_store.list_project_names(),
            procurement_linked=procurement_store.contract_has_refs(contract_id),
            error=request.args.get('error', ''),
        )
