"""HTTP adapters for comparison, negotiation, and award decisions."""

from __future__ import annotations

import os

from flask import (
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from routes.procurement_route_support import (
    error_redirect,
    form_error,
    money,
    project_or_404,
)
from services import (
    award_service,
    comparison_service,
    negotiation_service,
    project_document_service,
)


XLSX_MIMETYPE = (
    'application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.sheet'
)
DOCX_MIMETYPE = (
    'application/vnd.openxmlformats-officedocument.'
    'wordprocessingml.document'
)


def procurement_comparison(project_id):
    project_or_404(project_id)
    view = comparison_service.comparison_view(project_id)
    return render_template(
        'procurement/quote_compare.html',
        view=view,
        money=money,
        error=request.args.get('error', ''),
    )


def procurement_comparison_run(project_id):
    try:
        comparison_service.run_configured_comparison(
            project_id,
            request.form,
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_comparison',
            exc,
            exc_info=True,
            project_id=project_id,
        )
    return redirect(
        url_for(
            'procurement.procurement_comparison',
            project_id=project_id,
        )
    )


def procurement_comparison_export(project_id):
    try:
        path = comparison_service.export_comparison_excel(
            project_id
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_comparison',
            exc,
            exc_info=True,
            project_id=project_id,
        )
    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path),
        mimetype=XLSX_MIMETYPE,
    )


def procurement_clarifications_generate(project_id):
    try:
        comparison_service.generate_clarifications(project_id)
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_comparison',
            exc,
            exc_info=True,
            project_id=project_id,
        )
    return redirect(
        url_for(
            'procurement.procurement_project_detail',
            project_id=project_id,
        )
        + '#clarifications'
    )


def procurement_clarification_update(question_id):
    project_id = request.form.get(
        'project_id',
        type=int,
    )
    if not project_id or project_id < 1:
        return '采购项目 ID 无效', 400
    try:
        comparison_service.update_clarification(
            project_id,
            question_id,
            request.form,
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
        + '#clarifications'
    )


def procurement_award(project_id):
    project = project_or_404(project_id)
    view = award_service.award_view(project_id)
    if request.method == 'POST':
        try:
            if request.form.get('award_mode') == 'split':
                award_service.create_split_award(
                    project_id,
                    request.form,
                )
            else:
                supplier_id = int(
                    request.form.get('supplier_id', 0)
                )
                award_service.create_award(
                    project_id,
                    supplier_id,
                    request.form,
                )
            return redirect(
                url_for(
                    'procurement.procurement_project_detail',
                    project_id=project_id,
                )
            )
        except Exception as exc:
            return render_template(
                'procurement/award.html',
                project=project,
                quotes=view['quotes'],
                split_rows=view['split_rows'],
                award=view['award'],
                error=form_error(
                    '成交建议确认失败',
                    exc,
                ),
                money=money,
            ), 400
    return render_template(
        'procurement/award.html',
        project=project,
        quotes=view['quotes'],
        split_rows=view['split_rows'],
        award=view['award'],
        error=request.args.get('error', ''),
        money=money,
    )


def procurement_negotiation(project_id):
    project_or_404(project_id)
    if request.method == 'POST':
        try:
            negotiation_service.save_round(
                project_id,
                request.form,
            )
            return redirect(
                url_for(
                    'procurement.procurement_negotiation',
                    project_id=project_id,
                )
            )
        except Exception as exc:
            error = form_error('谈判操作失败', exc)
    else:
        error = request.args.get('error', '')
    view = negotiation_service.negotiation_view(
        project_id,
        request.args.get('round_no', type=int),
    )
    return render_template(
        'procurement/negotiation.html',
        view=view,
        error=error,
        money=money,
    )


def procurement_negotiation_plan(project_id):
    project_or_404(project_id)
    try:
        defaults = (
            project_document_service.negotiation_plan_defaults(
                project_id
            )
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_project_detail',
            exc,
            exc_info=True,
            project_id=project_id,
        )
    if request.method == 'POST':
        try:
            result = (
                project_document_service
                .generate_negotiation_plan(
                    project_id,
                    request.form,
                    return_info=True,
                )
            )
            return send_file(
                result['path'],
                as_attachment=True,
                download_name=result['download_name'],
                mimetype=DOCX_MIMETYPE,
            )
        except Exception as exc:
            plan = {
                **defaults['plan'],
                **{
                    key: request.form.get(
                        key,
                        defaults['plan'].get(key, ''),
                    )
                    for key in defaults['plan']
                },
            }
            return render_template(
                'procurement/negotiation_plan.html',
                view=defaults,
                plan=plan,
                error=form_error(
                    '谈判预案生成失败',
                    exc,
                ),
            ), 400
    return render_template(
        'procurement/negotiation_plan.html',
        view=defaults,
        plan=defaults['plan'],
        error=request.args.get('error', ''),
    )


def register_procurement_decision_routes(bp):
    routes = (
        (
            '/procurement/projects/<int:project_id>/comparison',
            procurement_comparison,
            ['GET'],
        ),
        (
            '/procurement/projects/<int:project_id>/comparison/run',
            procurement_comparison_run,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/comparison/export',
            procurement_comparison_export,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/'
            'clarifications/generate',
            procurement_clarifications_generate,
            ['POST'],
        ),
        (
            '/procurement/clarifications/<int:question_id>',
            procurement_clarification_update,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/award',
            procurement_award,
            ['GET', 'POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/negotiation',
            procurement_negotiation,
            ['GET', 'POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/'
            'negotiation/plan',
            procurement_negotiation_plan,
            ['GET', 'POST'],
        ),
    )
    for rule, view_func, methods in routes:
        bp.add_url_rule(
            rule,
            view_func=view_func,
            methods=methods,
        )
