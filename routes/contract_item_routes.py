"""HTTP adapters for contract product baselines."""

from __future__ import annotations

from flask import redirect, render_template, request, url_for

from core.domain_errors import NotFoundError
from services import production_commands, production_queries
from utils.production_forms import contract_item_rows


def _not_found_response(exc):
    return exc.public_message, exc.status_code


def register_contract_item_routes(bp):
    @bp.route(
        '/contracts/<int:contract_id>/items',
        methods=['GET', 'POST'],
    )
    def contract_items_page(contract_id):
        error = request.args.get('error', '')
        try:
            context = production_queries.contract_item_page(contract_id)
            if request.method == 'POST':
                production_commands.save_contract_items(
                    contract_id,
                    contract_item_rows(request.form),
                    operator=str(
                        request.form.get('operator', '') or ''
                    ).strip(),
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
