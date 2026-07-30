"""HTTP and JSON adapters for payment-plan views and actions."""

from __future__ import annotations

from flask import jsonify, redirect, render_template, request, url_for

from core.domain_errors import NotFoundError
from routes.workspace_navigation import contract_detail_location
from services import payment_commands, payment_queries
from utils.field_utils import float_or_none
from utils.payment_forms import (
    normalized_form_date,
    parse_plan_ids,
    payment_filter_args,
)


def _payment_redirect(form_or_args):
    raw_contract_id = str(
        form_or_args.get('return_contract_id', '') or ''
    ).strip()
    if raw_contract_id:
        try:
            contract_id = int(raw_contract_id)
        except ValueError:
            contract_id = 0
        if contract_id > 0:
            return redirect(
                contract_detail_location(
                    contract_id,
                    form_or_args,
                    default_tab='payments',
                )
            )
    return redirect(
        url_for(
            'payments.payment_plan_list',
            **payment_filter_args(form_or_args),
        )
    )


def register_payment_plan_routes(bp, today_provider):
    @bp.get('/api/payments/due-soon')
    def api_payments_due_soon():
        days = request.args.get('days', 7, type=int)
        return jsonify(payment_queries.due_soon_payload(days))

    @bp.get('/payment-plans')
    def payment_plan_list():
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        context = payment_queries.payment_plan_page(
            payment_filter_args(request.args),
            page,
            today_provider(),
        )
        return render_template('payment_plans.html', **context)

    @bp.post('/payment-plans/batch-confirm')
    def payment_plans_batch_confirm():
        try:
            plan_ids = parse_plan_ids(request.form.get('ids'))
            payment_commands.batch_confirm_payment_plans(plan_ids)
        except ValueError as exc:
            return str(exc), 400
        return _payment_redirect(request.form)

    @bp.post('/payment-plans/batch-paid')
    def payment_plans_batch_paid():
        try:
            plan_ids = parse_plan_ids(request.form.get('ids'))
            paid_date = normalized_form_date(
                request.form,
                'paid_date',
                today_provider().strftime('%Y-%m-%d'),
            )
            payment_commands.batch_mark_payment_plans_paid(
                plan_ids, paid_date
            )
        except ValueError as exc:
            return str(exc), 400
        return _payment_redirect(request.form)

    @bp.post('/payment-plans/<int:plan_id>/quick-update')
    def payment_plan_quick_update(plan_id):
        action = str(request.form.get('action', '') or '').strip()
        try:
            paid_date = ''
            paid_amount = None
            if action == 'paid':
                paid_date = normalized_form_date(
                    request.form,
                    'paid_date',
                    today_provider().strftime('%Y-%m-%d'),
                )
            elif action == 'partial':
                paid_date = normalized_form_date(
                    request.form, 'paid_date'
                )
                paid_amount = float_or_none(
                    request.form.get('paid_amount')
                )
            payment_commands.quick_update_payment_plan(
                plan_id,
                action,
                paid_date=paid_date,
                paid_amount=paid_amount,
            )
        except NotFoundError as exc:
            return exc.public_message, exc.status_code
        except ValueError as exc:
            return str(exc), 400
        return _payment_redirect(request.form)
