"""HTTP adapters for contract payment configuration."""

from __future__ import annotations

from flask import redirect, request

from core.domain_errors import NotFoundError
from routes.workspace_navigation import contract_detail_location
from services import payment_commands
from utils.payment_forms import (
    contract_serial_entries,
    payment_plan_changes,
    payment_rule_event,
    payment_rule_values,
)


def _contract_redirect(contract_id, source, error=''):
    return redirect(
        contract_detail_location(
            contract_id,
            source,
            default_tab='payments',
            error=error,
        )
    )


def _not_found_response(exc):
    return exc.public_message, exc.status_code


def register_contract_payment_routes(bp):
    @bp.post('/contracts/<int:contract_id>/serials/sync')
    def contract_serials_sync(contract_id):
        try:
            payment_commands.sync_contract_serials(contract_id)
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            return _contract_redirect(
                contract_id, request.form, error=str(exc)
            )
        return _contract_redirect(contract_id, request.form)

    @bp.post('/contracts/<int:contract_id>/serials/save')
    def contract_serials_save(contract_id):
        try:
            entries = contract_serial_entries(
                request.form,
                payment_commands.contract_serial_limit(),
            )
            payment_commands.save_contract_serials(contract_id, entries)
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            message = str(exc)
            if message.startswith('发次数量'):
                return message, 400
            return _contract_redirect(
                contract_id, request.form, error=message
            )
        return _contract_redirect(contract_id, request.form)

    @bp.post('/contracts/<int:contract_id>/serials/bulk-amount')
    def contract_serials_bulk_amount(contract_id):
        try:
            payment_commands.set_contract_serial_bulk_amount(
                contract_id,
                request.form.get('bulk_amount', ''),
                blank_only=request.form.get('replace_existing') != '1',
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            return _contract_redirect(
                contract_id, request.form, error=str(exc)
            )
        return _contract_redirect(contract_id, request.form)

    @bp.post(
        '/contracts/<int:contract_id>/payment-rules/'
        '<int:rule_id>/status'
    )
    def payment_rule_status(contract_id, rule_id):
        try:
            payment_commands.set_payment_rule_status(
                contract_id,
                rule_id,
                str(request.form.get('status', '') or '').strip(),
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            return _contract_redirect(
                contract_id, request.form, error=str(exc)
            )
        return _contract_redirect(contract_id, request.form)

    @bp.post(
        '/contracts/<int:contract_id>/payment-rules/'
        '<int:rule_id>/edit'
    )
    def payment_rule_edit(contract_id, rule_id):
        try:
            values = payment_rule_values(request.form)
            payment_commands.update_payment_rule(
                contract_id, rule_id, values
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except (TypeError, ValueError) as exc:
            return _contract_redirect(
                contract_id, request.form, error=str(exc)
            )
        return _contract_redirect(contract_id, request.form)

    @bp.post(
        '/contracts/<int:contract_id>/payment-rules/'
        '<int:rule_id>/trigger'
    )
    def payment_rule_trigger(contract_id, rule_id):
        try:
            event = payment_rule_event(request.form)
            payment_commands.trigger_payment_rule(
                contract_id, rule_id, event
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            return _contract_redirect(
                contract_id, request.form, error=str(exc)
            )
        return _contract_redirect(contract_id, request.form)

    @bp.post('/contracts/<int:contract_id>/payments/save')
    def payment_plans_save(contract_id):
        try:
            changes = payment_plan_changes(request.form)
            payment_commands.save_payment_plans(contract_id, changes)
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            return str(exc), 400
        return _contract_redirect(contract_id, request.form)

    @bp.post('/contracts/<int:contract_id>/payments/confirm-all')
    def payment_plans_confirm_all(contract_id):
        payment_commands.confirm_all_payment_plans(contract_id)
        return _contract_redirect(contract_id, request.form)
