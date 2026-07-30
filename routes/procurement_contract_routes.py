"""HTTP adapters for handing procurement data to the contract editor."""

from __future__ import annotations

from flask import (
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from routes.procurement_route_support import (
    error_redirect,
    form_error,
    money,
    project_or_404,
)
from runtime.flask_paths import current_runtime_paths
from services import (
    award_service,
    procurement_contract_handoff_service,
)


def register_procurement_contract_routes(bp):
    @bp.route(
        '/procurement/projects/<int:project_id>/to-contract',
        methods=['GET', 'POST'],
    )
    def procurement_to_contract(project_id):
        project = project_or_404(project_id)
        award = award_service.get_latest_award(project_id)
        if not award:
            return error_redirect(
                'procurement.procurement_award',
                '请先确认成交建议',
                project_id=project_id,
            )
        templates = award_service.list_contract_templates()
        if request.method == 'POST':
            try:
                result = (
                    procurement_contract_handoff_service
                    .create_award_editor_session(
                        project_id,
                        request.form.get(
                            'template_filename',
                            '',
                        ),
                        current_runtime_paths(),
                    )
                )
                session['sid'] = result.session_id
                return redirect(url_for('contracts.editor'))
            except Exception as exc:
                return render_template(
                    'procurement/to_contract.html',
                    project=project,
                    award=award,
                    templates=templates,
                    error=form_error(
                        '成交转合同失败',
                        exc,
                    ),
                    money=money,
                ), 400
        return render_template(
            'procurement/to_contract.html',
            project=project,
            award=award,
            templates=templates,
            error=request.args.get('error', ''),
            money=money,
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/direct-contract',
        methods=['GET', 'POST'],
    )
    def procurement_direct_contract(project_id):
        project = project_or_404(project_id)
        project['budget_amount'] = money(
            project.get('budget_minor')
        )
        project['target_price'] = money(
            project.get('target_price_minor')
        )
        templates = award_service.list_contract_templates()
        if request.method == 'POST':
            try:
                result = (
                    procurement_contract_handoff_service
                    .create_direct_editor_session(
                        project_id,
                        request.form.get(
                            'template_filename',
                            '',
                        ),
                        current_runtime_paths(),
                    )
                )
                session['sid'] = result.session_id
                return redirect(url_for('contracts.editor'))
            except Exception as exc:
                return render_template(
                    'procurement/direct_contract.html',
                    project=project,
                    templates=templates,
                    error=form_error(
                        '直接生成合同失败',
                        exc,
                    ),
                ), 400
        return render_template(
            'procurement/direct_contract.html',
            project=project,
            templates=templates,
            error=request.args.get('error', ''),
        )
