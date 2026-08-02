"""HTTP adapters for procurement project and workflow pages."""

from __future__ import annotations

from flask import (
    abort,
    redirect,
    render_template,
    request,
    url_for,
)

from routes.procurement_route_support import (
    error_redirect,
    form_error,
    money,
    project_or_404,
    stage_redirect_url,
)
from services import (
    historical_price_service,
    procurement_project_service,
)


def procurement_home():
    return redirect(
        url_for('procurement.procurement_projects')
    )


def procurement_projects():
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1
    result = procurement_project_service.list_projects(
        status=status,
        q=query,
        page=page,
    )
    return render_template(
        'procurement/project_list.html',
        result=result,
        q=query,
        status=status,
        project_statuses=(
            procurement_project_service.project_statuses()
        ),
    )


def procurement_history_prices():
    query = request.args.get('q', '').strip()
    if query:
        result = historical_price_service.price_assistance(query)
        strategy = (
            historical_price_service.negotiation_strategy(
                query
            )
        )
    else:
        result = {
            'rows': historical_price_service.search_prices(
                limit=200
            ),
            'count': 0,
            'min_minor': None,
            'max_minor': None,
            'median_minor': None,
            'suggested_target_minor': None,
        }
        strategy = ''
    return render_template(
        'procurement/history_prices.html',
        q=query,
        result=result,
        strategy=strategy,
        money=money,
    )


def procurement_project_new():
    if request.method == 'POST':
        try:
            project_id = procurement_project_service.create_project(
                request.form
            )
            return redirect(
                url_for(
                    'procurement.procurement_project_detail',
                    project_id=project_id,
                )
            )
        except Exception as exc:
            error = form_error('采购项目创建失败', exc)
            return render_template(
                'procurement/project_form.html',
                project=None,
                error=error,
            ), 400
    return render_template(
        'procurement/project_form.html',
        project=None,
        error='',
    )


def procurement_project_edit(project_id):
    project = project_or_404(project_id)
    if request.method == 'POST':
        try:
            procurement_project_service.update_project(
                project_id,
                request.form,
            )
            return redirect(
                url_for(
                    'procurement.procurement_project_detail',
                    project_id=project_id,
                )
            )
        except Exception as exc:
            form_data = {**project, **dict(request.form)}
            error = form_error('采购项目更新失败', exc)
            return render_template(
                'procurement/project_form.html',
                project=form_data,
                error=error,
            ), 400
    project['budget_amount'] = money(
        project.get('budget_minor')
    )
    project['target_price'] = money(
        project.get('target_price_minor')
    )
    return render_template(
        'procurement/project_form.html',
        project=project,
        error='',
    )


def procurement_project_detail(project_id):
    project = procurement_project_service.project_detail(
        project_id
    )
    if not project:
        abort(404, description='采购项目不存在')
    workflow = procurement_project_service.build_workflow_view(
        project_id
    )
    return render_template(
        'procurement/project_detail.html',
        project=project,
        workflow=workflow,
        error=request.args.get('error', ''),
        money=money,
    )


def procurement_workflow_jump(project_id):
    project_or_404(project_id)
    target_stage = request.form.get(
        'target_stage',
        '',
    ).strip()
    if request.form.get('mode') == 'enter':
        return redirect(
            stage_redirect_url(project_id, target_stage)
        )
    note = request.form.get('note', '').strip()
    try:
        procurement_project_service.jump_to_stage(
            project_id,
            target_stage,
            note,
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_project_detail',
            exc,
            project_id=project_id,
        )
    return redirect(
        stage_redirect_url(project_id, target_stage)
    )


def procurement_project_status(project_id):
    try:
        procurement_project_service.transition(
            project_id,
            request.form.get('status', ''),
            request.form.get('note', ''),
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_project_detail',
            exc,
            exc_info=True,
            project_id=project_id,
        )
    return redirect(
        url_for(
            'procurement.procurement_project_detail',
            project_id=project_id,
        )
    )


def register_procurement_project_routes(bp):
    bp.add_url_rule(
        '/procurement',
        view_func=procurement_home,
    )
    bp.add_url_rule(
        '/procurement/projects',
        view_func=procurement_projects,
    )
    bp.add_url_rule(
        '/procurement/history-prices',
        view_func=procurement_history_prices,
    )
    bp.add_url_rule(
        '/procurement/projects/new',
        view_func=procurement_project_new,
        methods=['GET', 'POST'],
    )
    bp.add_url_rule(
        '/procurement/projects/<int:project_id>/edit',
        view_func=procurement_project_edit,
        methods=['GET', 'POST'],
    )
    bp.add_url_rule(
        '/procurement/projects/<int:project_id>',
        view_func=procurement_project_detail,
    )
    bp.add_url_rule(
        '/procurement/projects/<int:project_id>/workflow/jump',
        view_func=procurement_workflow_jump,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/procurement/projects/<int:project_id>/status',
        view_func=procurement_project_status,
        methods=['POST'],
    )
