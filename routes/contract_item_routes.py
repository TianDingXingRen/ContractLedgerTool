"""HTTP adapters for contract product baselines."""

from __future__ import annotations

from flask import redirect, render_template, request, url_for

from core.domain_errors import NotFoundError
from services import production_commands, production_queries
from utils.production_forms import (
    contract_item_rows,
    contract_item_rows_for_redisplay,
)


def _not_found_response(exc):
    return exc.public_message, exc.status_code


def _submitted_item_context(context, rows, operator):
    """Overlay posted values on read-model rows for an error response."""
    existing = {
        int(item['id']): item
        for item in context.get('items', [])
        if item.get('id')
    }
    submitted = []
    for raw in rows:
        try:
            item_id = int(raw.get('id') or 0)
        except (TypeError, ValueError):
            item_id = 0
        item = dict(existing.get(item_id, {}))
        item.update(raw)
        item['id'] = raw.get('id', '')
        item.setdefault('issued_qty', 0)
        item.setdefault('remaining_qty', None)
        item.setdefault('amount', None)
        submitted.append(item)
    context['form_items'] = submitted
    context['operator'] = operator
    return context


def register_contract_item_routes(bp):
    @bp.route(
        '/contracts/<int:contract_id>/items',
        methods=['GET', 'POST'],
    )
    def contract_items_page(contract_id):
        error = request.args.get('error', '')
        submitted_rows = None
        operator = ''
        try:
            context = production_queries.contract_item_page(contract_id)
            if request.method == 'POST':
                operator = str(
                    request.form.get('operator', '') or ''
                ).strip()
                submitted_rows = contract_item_rows(request.form)
                production_commands.save_contract_items(
                    contract_id,
                    submitted_rows,
                    operator=operator,
                )
                return redirect(
                    url_for(
                        'production.contract_items_page',
                        contract_id=contract_id,
                    )
                )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            error = str(exc)
            context = production_queries.contract_item_page(contract_id)
            if request.method == 'POST' and submitted_rows is None:
                submitted_rows = contract_item_rows_for_redisplay(
                    request.form
                )
            if submitted_rows is not None:
                context = _submitted_item_context(
                    context, submitted_rows, operator
                )

        return (
            render_template(
                'contract_items.html',
                **context,
                error=error,
                message=request.args.get('message', ''),
            ),
            400 if error and request.method == 'POST' else 200,
        )

    @bp.post(
        '/contracts/<int:contract_id>/items/sync-procurement'
    )
    def contract_items_sync_procurement(contract_id):
        try:
            message = (
                production_commands.sync_contract_items_from_procurement(
                    contract_id
                )
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except ValueError as exc:
            return redirect(
                url_for(
                    'production.contract_items_page',
                    contract_id=contract_id,
                    error=str(exc),
                )
            )
        return redirect(
            url_for(
                'production.contract_items_page',
                contract_id=contract_id,
                message=message,
            )
        )
