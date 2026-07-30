"""HTTP adapters for production notice pages and drafts."""

from __future__ import annotations

from flask import redirect, render_template, request, url_for

from core.domain_errors import NotFoundError
from services import production_commands, production_queries
from utils.production_forms import (
    production_notice_header,
    production_notice_rows,
)


def _not_found_response(exc):
    return exc.public_message, exc.status_code


def register_production_notice_routes(bp):
    @bp.get('/production-notices')
    def production_notice_list():
        context = production_queries.production_notice_page(
            status=str(request.args.get('status', '') or '').strip(),
            contract_id=request.args.get('contract_id', type=int),
            page=max(
                1, request.args.get('page', 1, type=int) or 1
            ),
        )
        return render_template(
            'production_notice_list.html', **context
        )

    @bp.route(
        '/contracts/<int:contract_id>/production-notices/new',
        methods=['GET', 'POST'],
    )
    def production_notice_new(contract_id):
        try:
            context = (
                production_queries.new_production_notice_context(
                    contract_id
                )
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except production_queries.MissingContractItemsError as exc:
            return redirect(
                url_for(
                    'production.contract_items_page',
                    contract_id=contract_id,
                    error=str(exc),
                )
            )

        if request.method == 'POST':
            try:
                notice_id = (
                    production_commands.create_production_notice(
                        contract_id,
                        production_notice_header(request.form),
                        production_notice_rows(request.form),
                    )
                )
                return redirect(
                    url_for(
                        'production.production_notice_detail',
                        notice_id=notice_id,
                    )
                )
            except ValueError as exc:
                context = (
                    production_queries.new_production_notice_context(
                        contract_id, error=str(exc)
                    )
                )
                return (
                    render_template(
                        'production_notice_form.html', **context
                    ),
                    400,
                )
        return render_template(
            'production_notice_form.html', **context
        )

    @bp.get('/production-notices/<int:notice_id>')
    def production_notice_detail(notice_id):
        try:
            notice = production_queries.production_notice_detail(
                notice_id
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        return render_template(
            'production_notice_detail.html',
            notice=notice,
            error=request.args.get('error', ''),
            message=request.args.get('message', ''),
        )

    @bp.route(
        '/production-notices/<int:notice_id>/edit',
        methods=['GET', 'POST'],
    )
    def production_notice_edit(notice_id):
        try:
            context = (
                production_queries.editable_production_notice_context(
                    notice_id
                )
            )
        except NotFoundError as exc:
            return _not_found_response(exc)
        except production_queries.ProductionNoticeLockedError as exc:
            return redirect(
                url_for(
                    'production.production_notice_detail',
                    notice_id=notice_id,
                    error=str(exc),
                )
            )

        if request.method == 'POST':
            try:
                production_commands.save_production_notice_draft(
                    notice_id,
                    production_notice_header(request.form),
                    production_notice_rows(request.form),
                )
                return redirect(
                    url_for(
                        'production.production_notice_detail',
                        notice_id=notice_id,
                    )
                )
            except ValueError as exc:
                context = (
                    production_queries.editable_production_notice_context(
                        notice_id, error=str(exc)
                    )
                )
                return (
                    render_template(
                        'production_notice_form.html', **context
                    ),
                    400,
                )
        return render_template(
            'production_notice_form.html', **context
        )
