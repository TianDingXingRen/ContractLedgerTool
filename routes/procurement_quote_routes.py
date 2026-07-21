"""Confirmed supplier quote editing and deletion routes."""

from flask import abort, redirect, render_template, request, url_for

import procurement_store
from services import quote_service


def _quote_or_404(project_id, quote_id):
    quote = procurement_store.get_quote(quote_id)
    if not quote or quote['project_id'] != project_id:
        abort(404, description='供应商报价不存在')
    return quote


def _project_detail_with_quote_anchor(project_id, **values):
    return url_for('procurement_project_detail', project_id=project_id, **values) + '#quotes'


def register_quote_management_routes(bp, error_redirect, form_error, money):
    @bp.route(
        '/procurement/projects/<int:project_id>/quotes/<int:quote_id>/edit',
        methods=['GET', 'POST'],
    )
    def procurement_quote_edit(project_id, quote_id):
        quote = _quote_or_404(project_id, quote_id)
        items = procurement_store.get_quote_items(quote_id)
        if request.method == 'POST':
            try:
                quote_service.update_confirmed_quote(quote_id, request.form)
                return redirect(_project_detail_with_quote_anchor(project_id))
            except Exception as exc:
                error = form_error('供应商报价更新失败', exc)
                return render_template(
                    'procurement/quote_edit.html', project_id=project_id,
                    quote=quote, items=items, form=request.form, error=error, money=money,
                ), 400
        return render_template(
            'procurement/quote_edit.html', project_id=project_id,
            quote=quote, items=items, form=None, error='', money=money,
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/quotes/<int:quote_id>/delete',
        methods=['POST'],
    )
    def procurement_quote_delete(project_id, quote_id):
        _quote_or_404(project_id, quote_id)
        try:
            quote_service.delete_confirmed_quote(quote_id)
        except Exception as exc:
            response = error_redirect(
                'procurement_project_detail', exc, exc_info=True, project_id=project_id
            )
            response.headers['Location'] += '#quotes'
            return response
        return redirect(_project_detail_with_quote_anchor(project_id))
