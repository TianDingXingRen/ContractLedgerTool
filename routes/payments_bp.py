"""Payment plan routes: save, confirm, list, export, API."""

import json
import os
import uuid
from datetime import date, timedelta

from flask import render_template, request, redirect, url_for, send_file, jsonify

from routes.legacy_blueprint import LegacyEndpointBlueprint
from routes.workspace_navigation import contract_detail_location

import ledger_store
import xlsx_exporter
from utils import helpers
from utils.security import MAX_PLAN_ROWS
from utils.payment_forms import payment_row_from_form


def _payment_filter_args(form_or_args):
    return {
        'view': form_or_args.get('view', 'work') or 'work',
        'confirm_status': form_or_args.get('confirm_status', '').strip(),
        'payment_status': form_or_args.get('payment_status', '').strip(),
        'start_date': form_or_args.get('start_date', '').strip(),
        'end_date': form_or_args.get('end_date', '').strip(),
        'project_name': form_or_args.get('project_name', '').strip(),
    }


def _payment_redirect(form_or_args):
    raw_contract_id = str(form_or_args.get('return_contract_id', '') or '').strip()
    if raw_contract_id:
        try:
            contract_id = int(raw_contract_id)
        except ValueError:
            contract_id = 0
        if contract_id > 0:
            return redirect(contract_detail_location(
                contract_id, form_or_args, default_tab='payments'
            ))
    return redirect(url_for('payment_plan_list', **_payment_filter_args(form_or_args)))


def _parse_plan_ids(raw):
    try:
        ids = [int(item) for item in json.loads(raw or '[]')]
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError('付款计划 ID 列表无效')
    return list(dict.fromkeys(ids))


def _normalized_form_date(form, name, default=''):
    raw = str(form.get(name, '') or '').strip() or default
    normalized = helpers.normalize_date(raw)
    if not normalized:
        raise ValueError('日期格式无效，请使用 YYYY-MM-DD')
    return normalized


def _register_payment_rule_routes(bp):
    @bp.route(
        '/contracts/<int:contract_id>/payment-rules/<int:rule_id>/status',
        methods=['POST'],
    )
    def payment_rule_status(contract_id, rule_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        status = str(request.form.get('status', '') or '').strip()
        try:
            changed = ledger_store.set_payment_rule_confirm_status(
                rule_id, contract_id, status
            )
            if not changed:
                return '付款规则不存在', 404
        except ValueError as exc:
            return redirect(contract_detail_location(
                contract_id, request.form, default_tab='payments', error=str(exc)
            ))
        return redirect(contract_detail_location(
            contract_id, request.form, default_tab='payments'
        ))

    @bp.route(
        '/contracts/<int:contract_id>/payment-rules/<int:rule_id>/edit',
        methods=['POST'],
    )
    def payment_rule_edit(contract_id, rule_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404

        def optional_number(name, label):
            raw = str(request.form.get(name, '') or '').strip()
            if not raw:
                return None
            value = helpers.float_or_none(raw)
            if value is None:
                raise ValueError(f'{label}必须是有效数字')
            return value

        try:
            days_raw = str(request.form.get('trigger_days', '') or '').strip()
            trigger_days = int(days_raw) if days_raw else None
            if trigger_days is not None and not 0 <= trigger_days <= 36_500:
                raise ValueError('后置天数必须在0到36500之间')
            changed = ledger_store.update_payment_rule_manual(
                rule_id,
                contract_id,
                {
                    'phase_name': str(request.form.get('phase_name', '') or '').strip()[:120],
                    'scope': str(request.form.get('scope', 'contract') or 'contract'),
                    'trigger_event_type': str(request.form.get('trigger_event_type', 'other') or 'other')[:80],
                    'trigger_event': str(request.form.get('trigger_event', '') or '').strip()[:200],
                    'trigger_days': trigger_days,
                    'amount_basis': str(request.form.get('amount_basis', 'unknown') or 'unknown')[:80],
                    'amount_basis_text': str(request.form.get('amount_basis_text', '') or '').strip()[:300],
                    'ratio': optional_number('ratio', '付款比例'),
                    'explicit_amount': optional_number('explicit_amount', '合同明确金额'),
                    'calculated_amount': optional_number('calculated_amount', '比例计算金额'),
                    'repeat_mode': str(request.form.get('repeat_mode', 'once') or 'once'),
                },
            )
            if not changed:
                return '付款规则不存在', 404
        except (TypeError, ValueError) as exc:
            return redirect(contract_detail_location(
                contract_id, request.form, default_tab='payments', error=str(exc)
            ))
        return redirect(contract_detail_location(
            contract_id, request.form, default_tab='payments'
        ))

    @bp.route(
        '/contracts/<int:contract_id>/payment-rules/<int:rule_id>/trigger',
        methods=['POST'],
    )
    def payment_rule_trigger(contract_id, rule_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        reference_no = str(request.form.get('reference_no', '') or '').strip()
        event_date = str(request.form.get('event_date', '') or '').strip()
        reference_name = str(request.form.get('reference_name', '') or '').strip()
        amount_raw = str(request.form.get('base_amount', '') or '').strip()
        base_amount = helpers.float_or_none(amount_raw)
        if event_date and not helpers.normalize_date(event_date):
            return redirect(contract_detail_location(
                contract_id, request.form, default_tab='payments',
                error='业务事件日期格式无效，请使用 YYYY-MM-DD',
            ))
        try:
            ledger_store.create_payment_rule_event_instance(
                contract_id,
                rule_id,
                reference_no,
                event_date=helpers.normalize_date(event_date) if event_date else '',
                base_amount=base_amount,
                reference_name=reference_name,
            )
        except ValueError as exc:
            return redirect(contract_detail_location(
                contract_id, request.form, default_tab='payments', error=str(exc)
            ))
        return redirect(contract_detail_location(
            contract_id, request.form, default_tab='payments'
        ))

def _register_contract_payment_routes(bp):
    @bp.route('/contracts/<int:contract_id>/payments/save', methods=['POST'])
    def payment_plans_save(contract_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        try:
            count = int(request.form.get('plan_count', 0))
        except ValueError:
            count = 0
        if count > MAX_PLAN_ROWS:
            return f'付款计划行数不能超过 {MAX_PLAN_ROWS}', 400
        changes = []
        for idx in range(count):
            delete_flag = request.form.get(f'plan_{idx}_delete') == '1'
            plan_id = request.form.get(f'plan_{idx}_id', '').strip()
            if delete_flag:
                if plan_id:
                    try:
                        changes.append({'id': int(plan_id), 'delete': True})
                    except ValueError:
                        return '付款计划 ID 无效', 400
                continue
            try:
                row = payment_row_from_form(idx, request.form)
            except ValueError as e:
                return str(e), 400
            plan_id = row.pop('id', '')
            if plan_id:
                try:
                    plan_id = int(plan_id)
                except ValueError:
                    return '付款计划 ID 或状态无效', 400
                changes.append({'id': plan_id, 'data': row})
            elif helpers.has_payment_content(row):
                row['confirm_status'] = row.get('confirm_status') or 'confirmed'
                changes.append({'data': row})
        try:
            ledger_store.save_payment_plan_changes(contract_id, changes)
        except ValueError as e:
            return str(e), 400
        return redirect(contract_detail_location(
            contract_id, request.form, default_tab='payments'
        ))

    @bp.route('/contracts/<int:contract_id>/payments/confirm-all', methods=['POST'])
    def payment_plans_confirm_all(contract_id):
        plans = ledger_store.list_payment_plans(contract_id=contract_id, confirm_status='pending')
        confirmable_ids = [plan['id'] for plan in plans if helpers.can_bulk_confirm_payment(plan)]
        if confirmable_ids:
            ledger_store.batch_confirm_plans(confirmable_ids, contract_id)
        return redirect(contract_detail_location(
            contract_id, request.form, default_tab='payments'
        ))

def _register_payment_view_routes(bp):
    @bp.route('/api/payments/due-soon')
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
                'project_name': p.get('project_name', ''),
                'coverage_start': p.get('coverage_start'),
                'coverage_end': p.get('coverage_end'),
            } for p in payments],
        })

    @bp.route('/payment-plans')
    def payment_plan_list():
        view_mode = request.args.get('view', 'work').strip() or 'work'
        if view_mode not in {'work', 'detail'}:
            view_mode = 'work'
        confirm_status = request.args.get('confirm_status', '').strip()
        payment_status = request.args.get('payment_status', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        project_name = request.args.get('project_name', '').strip()
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        result = ledger_store.list_payment_plans(
            confirm_status=confirm_status,
            payment_status=payment_status,
            start_date=start_date,
            end_date=end_date,
            project_name=project_name,
            page=page,
        )
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        due_soon_end = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        for row in result['rows']:
            unpaid = (row.get('due_amount') or 0) - (row.get('paid_amount') or 0)
            due_date = row.get('due_date') or ''
            is_unpaid = row.get('payment_status') != 'paid'
            row['unpaid_amount'] = unpaid
            row['is_overdue'] = bool(due_date and due_date <= today_str and is_unpaid)
            row['is_due_soon'] = bool(due_date and today_str < due_date <= due_soon_end and is_unpaid)
        next_start, next_end = helpers.next_month_range()
        payment_summary = ledger_store.summarize_payment_plans(
            confirm_status=confirm_status,
            payment_status=payment_status,
            start_date=start_date,
            end_date=end_date,
            project_name=project_name,
            today=today,
        )
        return render_template(
            'payment_plans.html',
            plans=result['rows'],
            confirm_status=confirm_status,
            payment_status=payment_status,
            start_date=start_date,
            end_date=end_date,
            project_name=project_name,
            project_names=ledger_store.list_project_names(),
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
            next_start=next_start,
            next_end=next_end,
            today=today,
            due_soon_end=due_soon_end,
            view_mode=view_mode,
            payment_summary=payment_summary,
        )

def _register_payment_action_routes(bp):
    @bp.route('/payment-plans/batch-confirm', methods=['POST'])
    def payment_plans_batch_confirm():
        try:
            ids = _parse_plan_ids(request.form.get('ids'))
        except ValueError as e:
            return str(e), 400
        if len(ids) > MAX_PLAN_ROWS:
            return f'单次不能超过 {MAX_PLAN_ROWS} 条付款计划', 400
        ledger_store.batch_confirm_plans(ids)
        return _payment_redirect(request.form)

    @bp.route('/payment-plans/batch-paid', methods=['POST'])
    def payment_plans_batch_paid():
        try:
            ids = _parse_plan_ids(request.form.get('ids'))
            paid_date = _normalized_form_date(
                request.form, 'paid_date', date.today().strftime('%Y-%m-%d')
            )
        except ValueError as e:
            return str(e), 400
        if len(ids) > MAX_PLAN_ROWS:
            return f'单次不能超过 {MAX_PLAN_ROWS} 条付款计划', 400
        ledger_store.batch_mark_plans_paid(ids, paid_date)
        return _payment_redirect(request.form)

    @bp.route('/payment-plans/<int:plan_id>/quick-update', methods=['POST'])
    def payment_plan_quick_update(plan_id):
        action = request.form.get('action', '').strip()
        plan = ledger_store.get_payment_plan(plan_id)
        if not plan:
            return '付款计划不存在', 404
        try:
            if action == 'confirm':
                ledger_store.update_payment_plan(plan_id, {'confirm_status': 'confirmed'})
            elif action == 'paid':
                if plan.get('due_amount') is None:
                    return '缺少应付金额，不能直接标记已付', 400
                paid_date = _normalized_form_date(
                    request.form, 'paid_date', date.today().strftime('%Y-%m-%d')
                )
                ledger_store.update_payment_plan(plan_id, {
                    'confirm_status': 'confirmed',
                    'paid_amount': plan.get('due_amount'),
                    'paid_date': paid_date,
                })
            elif action == 'partial':
                paid_amount = helpers.float_or_none(request.form.get('paid_amount'))
                if paid_amount is None or paid_amount <= 0:
                    return '部分付款金额必须大于 0', 400
                paid_date = _normalized_form_date(request.form, 'paid_date')
                ledger_store.update_payment_plan(plan_id, {
                    'confirm_status': 'confirmed',
                    'paid_amount': paid_amount,
                    'paid_date': paid_date,
                })
            elif action == 'unpaid':
                ledger_store.update_payment_plan(plan_id, {
                    'paid_amount': 0,
                    'paid_date': '',
                })
            else:
                return '快捷操作无效', 400
        except ValueError as e:
            return str(e), 400
        return _payment_redirect(request.form)

def _register_payment_export_routes(bp):
    @bp.route('/payment-plans/export')
    def export_payment_plans():
        filters = _payment_filter_args(request.args)
        plans = ledger_store.list_payment_plans(
            confirm_status=filters['confirm_status'],
            payment_status=filters['payment_status'],
            start_date=filters['start_date'],
            end_date=filters['end_date'],
            project_name=filters['project_name'],
            page=0,
        )
        filename = f'payment_plans_{date.today().strftime("%Y%m%d")}_{uuid.uuid4().hex[:8]}.xlsx'
        output_path = os.path.join(helpers.OUTPUT_FOLDER, filename)
        xlsx_exporter.export_payment_plans(output_path, plans, title='付款计划')
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'付款计划_{date.today().strftime("%Y%m%d")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @bp.route('/payment-plans/export-next-month')
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

def register(app):
    bp = LegacyEndpointBlueprint('payments', __name__)
    _register_payment_rule_routes(bp)
    _register_contract_payment_routes(bp)
    _register_payment_view_routes(bp)
    _register_payment_action_routes(bp)
    _register_payment_export_routes(bp)
    app.register_blueprint(bp)
