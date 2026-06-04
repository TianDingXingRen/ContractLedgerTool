"""Payment plan routes: save, confirm, list, export, API."""

import os
import uuid

from flask import render_template, request, redirect, url_for, send_file, jsonify

import ledger_store
import xlsx_exporter
from utils import helpers
from utils.security import MAX_PLAN_ROWS, MAX_TEXT_VALUE_LENGTH, limit_text


def _payment_row_from_form(idx, form):
    prefix = f'plan_{idx}_'
    paid_amount = max(0, helpers.float_or_none(form.get(prefix + 'paid_amount')) or 0)
    ratio = helpers.float_or_none(form.get(prefix + 'ratio'))
    if ratio is not None and (ratio < 0 or ratio > 100):
        ratio = max(0.0, min(100.0, ratio))
    due_amount = helpers.float_or_none(form.get(prefix + 'due_amount'))
    if due_amount is not None:
        due_amount = max(0.0, due_amount)
    return {
        'id': form.get(prefix + 'id', '').strip(),
        'phase_name': limit_text(form.get(prefix + 'phase_name', '').strip(), 120),
        'payment_type': form.get(prefix + 'payment_type', 'conditional').strip() or 'conditional',
        'trigger_event': limit_text(form.get(prefix + 'trigger_event', '').strip(), 200),
        'trigger_days': helpers.int_or_none(form.get(prefix + 'trigger_days')),
        'expected_trigger_date': helpers.normalize_date(form.get(prefix + 'expected_trigger_date')) or form.get(prefix + 'expected_trigger_date', '').strip(),
        'due_date': helpers.normalize_date(form.get(prefix + 'due_date')) or form.get(prefix + 'due_date', '').strip(),
        'ratio': ratio,
        'due_amount': due_amount,
        'paid_amount': paid_amount,
        'paid_date': helpers.normalize_date(form.get(prefix + 'paid_date')) or form.get(prefix + 'paid_date', '').strip(),
        'condition_text': limit_text(form.get(prefix + 'condition_text', '').strip(), MAX_TEXT_VALUE_LENGTH),
        'source_text': limit_text(form.get(prefix + 'source_text', '').strip(), MAX_TEXT_VALUE_LENGTH),
        'confidence': form.get(prefix + 'confidence', 'low').strip() or 'low',
        'confirm_status': form.get(prefix + 'confirm_status', 'pending').strip() or 'pending',
        'payment_status': form.get(prefix + 'payment_status', 'unpaid').strip() or 'unpaid',
        'remark': limit_text(form.get(prefix + 'remark', '').strip(), 500),
    }


def register(app):
    @app.route('/contracts/<int:contract_id>/payments/save', methods=['POST'])
    def payment_plans_save(contract_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        try:
            count = int(request.form.get('plan_count', 0))
        except ValueError:
            count = 0
        if count > MAX_PLAN_ROWS:
            return f'付款计划行数不能超过 {MAX_PLAN_ROWS}', 400
        for idx in range(count):
            delete_flag = request.form.get(f'plan_{idx}_delete') == '1'
            plan_id = request.form.get(f'plan_{idx}_id', '').strip()
            if delete_flag:
                if plan_id:
                    try:
                        ledger_store.delete_payment_plan(int(plan_id), contract_id=contract_id)
                    except ValueError:
                        return '付款计划 ID 无效', 400
                continue
            row = _payment_row_from_form(idx, request.form)
            plan_id = row.pop('id', '')
            if plan_id:
                try:
                    updated = ledger_store.update_payment_plan(int(plan_id), row, contract_id=contract_id)
                except ValueError:
                    return '付款计划 ID 或状态无效', 400
                if updated == 0:
                    return '付款计划不存在或不属于当前合同', 404
            elif helpers.has_payment_content(row):
                row['confirm_status'] = row.get('confirm_status') or 'confirmed'
                try:
                    ledger_store.insert_payment_plan(contract_id, row)
                except ValueError as e:
                    return str(e), 400
        return redirect(url_for('contract_detail', contract_id=contract_id))

    @app.route('/contracts/<int:contract_id>/payments/confirm-all', methods=['POST'])
    def payment_plans_confirm_all(contract_id):
        plans = ledger_store.list_payment_plans(contract_id=contract_id, confirm_status='pending')
        for plan in plans:
            if helpers.can_bulk_confirm_payment(plan):
                ledger_store.update_payment_plan(plan['id'], {'confirm_status': 'confirmed'}, contract_id=contract_id)
        return redirect(url_for('contract_detail', contract_id=contract_id))

    @app.route('/api/payments/due-soon')
    def api_payments_due_soon():
        days = request.args.get('days', 7, type=int)
        days = max(0, min(days or 7, 365))
        payments = ledger_store.get_due_soon_payments(days=days)
        count = len(payments)
        total = sum(
            (p.get('due_amount') or 0) - (p.get('paid_amount') or 0)
            for p in payments
        )
        return jsonify({
            'count': count,
            'total_amount': round(total, 2),
            'payments': [{
                'id': p['id'],
                'contract_id': p['contract_id'],
                'contract_no': p.get('contract_no', ''),
                'contract_title': p.get('contract_title', ''),
                'phase_name': p.get('phase_name', ''),
                'due_date': p.get('due_date', ''),
                'due_amount': p.get('due_amount', 0),
                'paid_amount': p.get('paid_amount', 0),
                'counterparty': p.get('counterparty', ''),
                'owner': p.get('owner', ''),
            } for p in payments],
        })

    @app.route('/payment-plans')
    def payment_plan_list():
        confirm_status = request.args.get('confirm_status', '').strip()
        payment_status = request.args.get('payment_status', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        result = ledger_store.list_payment_plans(
            confirm_status=confirm_status,
            payment_status=payment_status,
            start_date=start_date,
            end_date=end_date,
            page=page,
        )
        next_start, next_end = helpers.next_month_range()
        return render_template(
            'payment_plans.html',
            plans=result['rows'],
            confirm_status=confirm_status,
            payment_status=payment_status,
            start_date=start_date,
            end_date=end_date,
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
            next_start=next_start,
            next_end=next_end,
        )

    @app.route('/payment-plans/export-next-month')
    def export_next_month_payments():
        start, end = helpers.next_month_range()
        plans = ledger_store.next_month_payment_plans(start, end)
        filename = f'next_month_payments_{start}_{end}_{uuid.uuid4().hex[:8]}.xlsx'
        output_path = os.path.join(helpers.OUTPUT_FOLDER, filename)
        xlsx_exporter.export_payment_plans(output_path, plans, title=f'{start} 至 {end} 付款计划')
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'下月付款计划_{start}_{end}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
