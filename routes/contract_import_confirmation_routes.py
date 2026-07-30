"""HTTP adapters for reviewing and confirming contract imports."""

from __future__ import annotations

from flask import (
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from services import contract_import_workflow
from utils.contract_import_forms import (
    plans_for_render,
    plans_from_form,
    rules_for_render,
    rules_from_form,
    summary_for_render,
    summary_from_form,
)


def _import_page_redirect():
    return redirect(
        url_for(
            'contract_import.contract_import',
            error='合同导入会话已过期，请重新上传',
        )
    )


def _contract_redirect(contract_id):
    return redirect(
        url_for(
            'contracts.contract_detail',
            contract_id=contract_id,
        )
    )


def _render_review(
    sid,
    data,
    *,
    error='',
    submitted_summary=None,
    submitted_plans=None,
    submitted_rules=None,
    duplicate_contract=None,
    status=200,
):
    context = contract_import_workflow.review_model(
        sid,
        data,
        submitted_summary=submitted_summary,
        submitted_plans=submitted_plans,
        submitted_rules=submitted_rules,
        duplicate_contract=duplicate_contract,
    )
    return render_template(
        'contract_import_review.html',
        **context,
        error=error,
    ), status


def register_contract_import_confirmation_routes(bp):
    @bp.get('/contracts/import/<sid>/review')
    def contract_import_review(sid):
        try:
            data, confirmed_id = (
                contract_import_workflow.review_import(
                    sid, session.get('contract_import_sid')
                )
            )
        except (FileNotFoundError, ValueError):
            return _import_page_redirect()
        if confirmed_id:
            return _contract_redirect(confirmed_id)
        return _render_review(sid, data)

    @bp.post('/contracts/import/<sid>/confirm')
    def contract_import_confirm(sid):
        expected_sid = session.get('contract_import_sid')
        try:
            data = contract_import_workflow.load_import_session(
                sid, expected_sid
            )
        except (FileNotFoundError, ValueError):
            return _import_page_redirect()
        if data.get('confirmed_contract_id'):
            return _contract_redirect(
                data['confirmed_contract_id']
            )

        submitted_summary = summary_for_render(request.form)
        submitted_plans = plans_for_render(request.form)
        submitted_rules = rules_for_render(request.form)
        summary = None
        try:
            summary = summary_from_form(request.form)
            plans = plans_from_form(request.form)
            rules = rules_from_form(request.form)
        except ValueError as exc:
            return _render_review(
                sid,
                data,
                error=str(exc),
                submitted_summary=summary or submitted_summary,
                submitted_plans=submitted_plans,
                submitted_rules=submitted_rules,
                status=409,
            )

        try:
            contract_id = contract_import_workflow.confirm_import(
                sid,
                expected_sid,
                summary=summary,
                plans=plans,
                rules=rules,
                importer=current_app.extensions[
                    'contract_tool'
                ].contract_import,
            )
            return _contract_redirect(contract_id)
        except contract_import_workflow.ImportSessionExpired:
            return _import_page_redirect()
        except (
            contract_import_workflow.ImportConfirmationRejected
        ) as exc:
            return _render_review(
                sid,
                exc.data,
                error=str(exc),
                submitted_summary=summary,
                submitted_plans=submitted_plans,
                submitted_rules=submitted_rules,
                duplicate_contract=exc.duplicate_contract,
                status=409,
            )
        except contract_import_workflow.ImportConfirmationFailed as exc:
            return _render_review(
                sid,
                exc.data,
                error=str(exc),
                submitted_summary=summary,
                submitted_plans=submitted_plans,
                submitted_rules=submitted_rules,
                status=500,
            )

    @bp.post('/contracts/import/<sid>/cancel')
    def contract_import_cancel(sid):
        contract_import_workflow.cancel_import(
            sid, session.get('contract_import_sid')
        )
        if session.get('contract_import_sid') == sid:
            session.pop('contract_import_sid', None)
        return redirect(url_for('contracts.contract_ledger'))
