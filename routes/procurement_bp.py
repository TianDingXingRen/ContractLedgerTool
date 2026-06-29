"""Procurement pre-workbench routes."""

from __future__ import annotations

import logging
import os
import uuid
from decimal import Decimal

from flask import abort, redirect, render_template, request, send_file, session, url_for

import procurement_store
import template_def
from services import (
    award_service, comparison_service, historical_price_service, negotiation_service,
    procurement_file_service,
    procurement_project_service, project_document_service, quote_mapping_service,
    quote_service,
)
from utils import helpers
from utils.errors import GENERIC_ERROR

_log = logging.getLogger('contract_tool')

_ALLOWED_EXCEL_EXTENSIONS = {'.xlsx', '.xls'}
_USER_FACING_ERRORS = (ValueError, FileNotFoundError)


def _is_allowed_excel(filename):
    """校验文件扩展名是否为允许的 Excel 类型。"""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in _ALLOWED_EXCEL_EXTENSIONS


def _money(value):
    if value is None:
        return ''
    return f'{Decimal(int(value)) / 100:.2f}'


def _project_or_404(project_id):
    project = procurement_store.get_project(project_id)
    if not project:
        abort(404, description='采购项目不存在')
    return project


def _classified_error_message(error):
    if isinstance(error, _USER_FACING_ERRORS):
        return str(error), False
    if isinstance(error, Exception):
        return GENERIC_ERROR, True
    return str(error), False


def _form_error(context, error):
    message, is_system_error = _classified_error_message(error)
    if is_system_error:
        _log.error('%s: %s', context, error, exc_info=True)
    else:
        _log.info('%s: %s', context, error)
    return message


def _error_redirect(endpoint, message, exc_info=None, **values):
    error_message, is_system_error = _classified_error_message(message)
    if is_system_error or (exc_info and error_message == GENERIC_ERROR):
        _log.error('采购操作错误: %s', message, exc_info=exc_info)
    elif exc_info:
        _log.info('采购操作错误: %s', message)
    values['error'] = error_message
    return redirect(url_for(endpoint, **values))


def _stage_redirect_url(project_id, stage):
    if stage == 'project':
        return url_for('procurement_project_edit', project_id=project_id)
    if stage == 'items':
        return url_for('procurement_project_detail', project_id=project_id) + '#items'
    if stage == 'suppliers':
        return url_for('procurement_project_detail', project_id=project_id) + '#suppliers'
    if stage == 'quotes':
        return url_for('procurement_quote_import', project_id=project_id)
    if stage == 'comparison':
        return url_for('procurement_comparison', project_id=project_id)
    if stage == 'negotiation':
        return url_for('procurement_negotiation', project_id=project_id)
    if stage == 'award':
        return url_for('procurement_award', project_id=project_id)
    if stage == 'contract':
        return url_for('procurement_direct_contract', project_id=project_id)
    if stage == 'archive':
        return url_for('procurement_project_archive', project_id=project_id)
    return url_for('procurement_project_detail', project_id=project_id)


def _project_section_url(project_id, section):
    return url_for('procurement_project_detail', project_id=project_id) + f'#{section}'


def register(app):
    @app.route('/procurement')
    def procurement_home():
        return redirect(url_for('procurement_projects'))

    @app.route('/procurement/projects')
    def procurement_projects():
        q = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        result = procurement_store.list_projects(status=status, q=q, page=page)
        return render_template(
            'procurement/project_list.html', result=result, q=q, status=status,
            project_statuses=procurement_store.PROJECT_STATUSES,
        )

    @app.route('/procurement/history-prices')
    def procurement_history_prices():
        q = request.args.get('q', '').strip()
        result = historical_price_service.price_assistance(q) if q else {
            'rows': historical_price_service.search_prices(limit=200), 'count': 0,
            'min_minor': None, 'max_minor': None, 'median_minor': None,
            'suggested_target_minor': None,
        }
        strategy = historical_price_service.negotiation_strategy(q) if q else ''
        return render_template(
            'procurement/history_prices.html', q=q, result=result,
            strategy=strategy, money=_money,
        )

    @app.route('/procurement/projects/new', methods=['GET', 'POST'])
    def procurement_project_new():
        if request.method == 'POST':
            try:
                project_id = procurement_project_service.create_project(request.form)
                return redirect(url_for('procurement_project_detail', project_id=project_id))
            except Exception as exc:
                error = _form_error('采购项目创建失败', exc)
                return render_template('procurement/project_form.html', project=None, error=error), 400
        return render_template('procurement/project_form.html', project=None, error='')

    @app.route('/procurement/projects/<int:project_id>/edit', methods=['GET', 'POST'])
    def procurement_project_edit(project_id):
        project = _project_or_404(project_id)
        if request.method == 'POST':
            try:
                procurement_project_service.update_project(project_id, request.form)
                return redirect(url_for('procurement_project_detail', project_id=project_id))
            except Exception as exc:
                form_data = {**project, **dict(request.form)}
                error = _form_error('采购项目更新失败', exc)
                return render_template('procurement/project_form.html', project=form_data, error=error), 400
        project['budget_amount'] = _money(project.get('budget_minor'))
        project['target_price'] = _money(project.get('target_price_minor'))
        return render_template('procurement/project_form.html', project=project, error='')

    @app.route('/procurement/projects/<int:project_id>')
    def procurement_project_detail(project_id):
        project = procurement_project_service.project_detail(project_id)
        if not project:
            abort(404, description='采购项目不存在')
        workflow = procurement_project_service.build_workflow_view(project_id)
        return render_template(
            'procurement/project_detail.html', project=project,
            workflow=workflow, error=request.args.get('error', ''), money=_money,
        )

    @app.route('/procurement/projects/<int:project_id>/workflow/jump', methods=['POST'])
    def procurement_workflow_jump(project_id):
        _project_or_404(project_id)
        target_stage = request.form.get('target_stage', '').strip()
        note = request.form.get('note', '').strip()
        try:
            procurement_project_service.jump_to_stage(project_id, target_stage, note)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, project_id=project_id)
        return redirect(_stage_redirect_url(project_id, target_stage))

    @app.route('/procurement/projects/<int:project_id>/status', methods=['POST'])
    def procurement_project_status(project_id):
        try:
            procurement_project_service.transition(
                project_id, request.form.get('status', ''), request.form.get('note', '')
            )
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return redirect(url_for('procurement_project_detail', project_id=project_id))

    @app.route('/procurement/projects/<int:project_id>/items', methods=['POST'])
    def procurement_item_add(project_id):
        try:
            procurement_project_service.add_item(project_id, request.form)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return redirect(_project_section_url(project_id, 'items'))

    @app.route('/procurement/projects/<int:project_id>/items/bulk', methods=['GET', 'POST'])
    def procurement_items_bulk(project_id):
        project = _project_or_404(project_id)
        if request.method == 'POST':
            try:
                file = request.files.get('file')
                if file and file.filename:
                    procurement_project_service.add_items_from_excel(project_id, file)
                else:
                    procurement_project_service.add_items_from_paste(
                        project_id, request.form.get('pasted_rows', '')
                    )
                return redirect(url_for('procurement_project_detail', project_id=project_id))
            except Exception as exc:
                error = _form_error('采购明细批量导入失败', exc)
                return render_template(
                    'procurement/items_bulk.html', project=project,
                    pasted_rows=request.form.get('pasted_rows', ''), error=error,
                ), 400
        return render_template(
            'procurement/items_bulk.html', project=project, pasted_rows='', error=''
        )

    @app.route('/procurement/projects/<int:project_id>/items/export')
    def procurement_items_export(project_id):
        try:
            path = project_document_service.export_project_items(project_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/procurement/projects/<int:project_id>/items/<int:item_id>/delete', methods=['POST'])
    def procurement_item_delete(project_id, item_id):
        try:
            procurement_store.delete_project_item(project_id, item_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return redirect(url_for('procurement_project_detail', project_id=project_id))

    @app.route('/procurement/projects/<int:project_id>/items/<int:item_id>/edit', methods=['GET', 'POST'])
    def procurement_item_edit(project_id, item_id):
        _project_or_404(project_id)
        item = procurement_store.get_project_item(item_id)
        if not item or item['project_id'] != project_id:
            abort(404, description='采购明细不存在')
        if request.method == 'POST':
            try:
                procurement_project_service.update_item(project_id, item_id, request.form)
                return redirect(url_for('procurement_project_detail', project_id=project_id))
            except Exception as exc:
                error = _form_error('采购明细更新失败', exc)
                return render_template(
                    'procurement/item_form.html', project_id=project_id,
                    item={**item, **request.form}, error=error,
                ), 400
        return render_template('procurement/item_form.html', project_id=project_id, item=item, error='')

    @app.route('/procurement/projects/<int:project_id>/suppliers', methods=['POST'])
    def procurement_supplier_add(project_id):
        try:
            procurement_project_service.add_supplier(project_id, request.form)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return redirect(_project_section_url(project_id, 'suppliers'))

    @app.route('/procurement/projects/<int:project_id>/quote-template')
    def procurement_quote_template_selected(project_id):
        supplier_id = request.args.get('supplier_id', type=int)
        if not supplier_id:
            return _error_redirect(
                'procurement_quote_import', '请选择候选供应商后下载模板',
                project_id=project_id,
            )
        try:
            path = quote_service.generate_quote_template(project_id, supplier_id)
        except Exception as exc:
            return _error_redirect('procurement_quote_import', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/procurement/projects/<int:project_id>/suppliers/<int:supplier_id>/delete', methods=['POST'])
    def procurement_supplier_delete(project_id, supplier_id):
        try:
            procurement_store.delete_project_supplier(project_id, supplier_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return redirect(url_for('procurement_project_detail', project_id=project_id))

    @app.route('/procurement/projects/<int:project_id>/suppliers/<int:supplier_id>/edit', methods=['GET', 'POST'])
    def procurement_supplier_edit(project_id, supplier_id):
        _project_or_404(project_id)
        supplier = procurement_store.get_project_supplier(supplier_id)
        if not supplier or supplier['project_id'] != project_id:
            abort(404, description='候选供应商不存在')
        if request.method == 'POST':
            try:
                procurement_project_service.update_supplier(project_id, supplier_id, request.form)
                return redirect(url_for('procurement_project_detail', project_id=project_id))
            except Exception as exc:
                error = _form_error('候选供应商更新失败', exc)
                return render_template(
                    'procurement/supplier_form.html', project_id=project_id,
                    supplier={**supplier, **request.form}, error=error,
                ), 400
        return render_template(
            'procurement/supplier_form.html', project_id=project_id, supplier=supplier, error=''
        )

    @app.route('/procurement/projects/<int:project_id>/quote-template/<int:supplier_id>')
    def procurement_quote_template(project_id, supplier_id):
        try:
            path = quote_service.generate_quote_template(project_id, supplier_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/procurement/projects/<int:project_id>/inquiry')
    def procurement_inquiry_document(project_id):
        try:
            path = project_document_service.generate_inquiry_letter(project_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.route('/procurement/projects/<int:project_id>/clarifications/document')
    def procurement_clarification_document(project_id):
        try:
            path = project_document_service.generate_clarification_letter(
                project_id, request.args.get('supplier_id', type=int)
            )
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.route('/procurement/projects/<int:project_id>/award/document')
    def procurement_award_document(project_id):
        try:
            path = project_document_service.generate_award_recommendation(project_id)
        except Exception as exc:
            return _error_redirect('procurement_award', exc, exc_info=True, project_id=project_id)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.route('/procurement/files/<int:file_id>/download')
    def procurement_file_download(file_id):
        file_record = procurement_store.get_project_file(file_id)
        if not file_record:
            abort(404, description='项目文件不存在')
        try:
            path = procurement_file_service.absolute_path(file_record['relative_path'])
        except ValueError as exc:
            abort(400, description=str(exc))
        if not path.is_file():
            abort(404, description='项目文件已丢失')
        return send_file(
            path, as_attachment=True,
            download_name=file_record.get('original_name') or path.name,
        )

    @app.route('/procurement/projects/<int:project_id>/erp-oa-summary')
    def procurement_erp_oa_summary(project_id):
        try:
            path = project_document_service.generate_erp_oa_summary(project_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/procurement/projects/<int:project_id>/archive')
    def procurement_project_archive(project_id):
        try:
            path = project_document_service.generate_project_archive(project_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path), mimetype='application/zip')

    @app.route('/procurement/projects/<int:project_id>/quotes/import', methods=['GET', 'POST'])
    def procurement_quote_import(project_id):
        project = _project_or_404(project_id)
        suppliers = procurement_store.list_project_suppliers(project_id)
        if request.method == 'POST':
            file = request.files.get('file')
            if not file or not file.filename:
                return render_template(
                    'procurement/quote_import.html', project=project, suppliers=suppliers,
                    error='请选择报价 Excel 文件',
                ), 400
            if not _is_allowed_excel(file.filename):
                return render_template(
                    'procurement/quote_import.html', project=project, suppliers=suppliers,
                    error='仅支持 .xlsx 或 .xls 格式的 Excel 文件',
                ), 400
            try:
                supplier_id = int(request.form.get('supplier_id', 0))
                quote_round = int(request.form.get('quote_round', 1))
                job_id = quote_service.create_import_job(
                    project_id, supplier_id, quote_round, file
                )
                return redirect(url_for('procurement_quote_preview', job_id=job_id))
            except Exception as exc:
                error = _form_error('报价导入失败', exc)
                return render_template(
                    'procurement/quote_import.html', project=project, suppliers=suppliers,
                    error=error,
                ), 400
        return render_template(
            'procurement/quote_import.html', project=project, suppliers=suppliers,
            error=request.args.get('error', ''),
        )

    @app.route('/procurement/projects/<int:project_id>/quotes/map', methods=['GET', 'POST'])
    def procurement_quote_mapping_upload(project_id):
        project = _project_or_404(project_id)
        suppliers = procurement_store.list_project_suppliers(project_id)
        if request.method == 'POST':
            file = request.files.get('file')
            if not file or not file.filename:
                return render_template(
                    'procurement/quote_mapping_upload.html', project=project,
                    suppliers=suppliers, error='请选择报价文件',
                ), 400
            if not _is_allowed_excel(file.filename):
                return render_template(
                    'procurement/quote_mapping_upload.html', project=project,
                    suppliers=suppliers, error='仅支持 .xlsx 或 .xls 格式的 Excel 文件',
                ), 400
            try:
                job_id = quote_mapping_service.create_mapping_job(
                    project_id, int(request.form.get('supplier_id', 0)),
                    int(request.form.get('quote_round', 1)), file,
                )
                return redirect(url_for('procurement_quote_mapping', job_id=job_id))
            except Exception as exc:
                error = _form_error('报价映射任务创建失败', exc)
                return render_template(
                    'procurement/quote_mapping_upload.html', project=project,
                    suppliers=suppliers, error=error,
                ), 400
        return render_template(
            'procurement/quote_mapping_upload.html', project=project,
            suppliers=suppliers, error=request.args.get('error', ''),
        )

    @app.route('/procurement/quote-mappings/<int:job_id>', methods=['GET', 'POST'])
    def procurement_quote_mapping(job_id):
        job = procurement_store.get_mapping_job(job_id)
        if not job:
            abort(404, description='字段映射任务不存在')
        if request.method == 'POST':
            try:
                import_job_id = quote_mapping_service.map_to_import_job(job_id, request.form)
                return redirect(url_for('procurement_quote_preview', job_id=import_job_id))
            except Exception as exc:
                error = _form_error(f'报价映射失败 (job {job_id})', exc)
        else:
            error = request.args.get('error', '')
        selected_name = request.args.get('table') or job['source']['tables'][0]['name']
        selected = next(
            (table for table in job['source']['tables'] if table['name'] == selected_name),
            job['source']['tables'][0],
        )
        headers = selected['rows'][0] if selected['rows'] else []
        return render_template(
            'procurement/quote_mapping.html', job=job, selected=selected,
            headers=headers, mapping_fields=quote_mapping_service.MAPPING_FIELDS,
            error=error,
        )

    @app.route('/procurement/quote-imports/<int:job_id>')
    def procurement_quote_preview(job_id):
        job = procurement_store.get_import_job(job_id)
        if not job:
            abort(404, description='报价导入任务不存在')
        return render_template('procurement/quote_preview.html', job=job, money=_money)

    @app.route('/procurement/quote-imports/<int:job_id>/confirm', methods=['POST'])
    def procurement_quote_confirm(job_id):
        job = procurement_store.get_import_job(job_id)
        if not job:
            abort(404, description='报价导入任务不存在')
        try:
            quote_service.confirm_import(job_id)
        except Exception as exc:
            return _error_redirect('procurement_quote_import', exc, exc_info=True, project_id=job['project_id'])
        return redirect(url_for('procurement_project_detail', project_id=job['project_id']))

    @app.route('/procurement/projects/<int:project_id>/comparison')
    def procurement_comparison(project_id):
        _project_or_404(project_id)
        view = comparison_service.comparison_view(project_id)
        return render_template(
            'procurement/quote_compare.html', view=view, money=_money,
            error=request.args.get('error', ''),
        )

    @app.route('/procurement/projects/<int:project_id>/comparison/run', methods=['POST'])
    def procurement_comparison_run(project_id):
        try:
            threshold = Decimal(str(request.form.get('threshold_percent') or 20))
            min_valid = int(request.form.get('min_valid_suppliers') or 2)
            if threshold < 0 or threshold > 100 or min_valid < 2 or min_valid > 20:
                raise ValueError('比价阈值或最小供应商数量超出范围')
            procurement_store.save_rule_config(project_id, {
                'price_threshold_percent': threshold,
                'min_valid_suppliers': min_valid,
                'require_same_price_basis': request.form.get('require_same_price_basis') == '1',
            })
            comparison_service.run_comparison(project_id, threshold)
        except Exception as exc:
            return _error_redirect('procurement_comparison', exc, exc_info=True, project_id=project_id)
        return redirect(url_for('procurement_comparison', project_id=project_id))

    @app.route('/procurement/projects/<int:project_id>/comparison/export')
    def procurement_comparison_export(project_id):
        try:
            path = comparison_service.export_comparison_excel(project_id)
        except Exception as exc:
            return _error_redirect('procurement_comparison', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/procurement/projects/<int:project_id>/clarifications/generate', methods=['POST'])
    def procurement_clarifications_generate(project_id):
        try:
            comparison_service.generate_clarifications(project_id)
        except Exception as exc:
            return _error_redirect('procurement_comparison', exc, exc_info=True, project_id=project_id)
        return redirect(url_for('procurement_project_detail', project_id=project_id) + '#clarifications')

    @app.route('/procurement/clarifications/<int:question_id>', methods=['POST'])
    def procurement_clarification_update(question_id):
        project_id = int(request.form.get('project_id', 0))
        try:
            procurement_store.update_clarification(question_id, request.form)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        return redirect(url_for('procurement_project_detail', project_id=project_id) + '#clarifications')

    @app.route('/procurement/projects/<int:project_id>/award', methods=['GET', 'POST'])
    def procurement_award(project_id):
        project = _project_or_404(project_id)
        quotes = procurement_store.get_latest_quotes(project_id)
        split_rows, _ = award_service.split_award_options(project_id)
        if request.method == 'POST':
            try:
                if request.form.get('award_mode') == 'split':
                    award_service.create_split_award(project_id, request.form)
                else:
                    supplier_id = int(request.form.get('supplier_id', 0))
                    award_service.create_award(project_id, supplier_id, request.form)
                return redirect(url_for('procurement_project_detail', project_id=project_id))
            except Exception as exc:
                error = _form_error('成交建议确认失败', exc)
                return render_template(
                    'procurement/award.html', project=project, quotes=quotes,
                    split_rows=split_rows, award=procurement_store.get_latest_award(project_id),
                    error=error, money=_money,
                ), 400
        return render_template(
            'procurement/award.html', project=project, quotes=quotes,
            split_rows=split_rows, award=procurement_store.get_latest_award(project_id),
            error=request.args.get('error', ''), money=_money,
        )

    @app.route('/procurement/projects/<int:project_id>/negotiation', methods=['GET', 'POST'])
    def procurement_negotiation(project_id):
        _project_or_404(project_id)
        if request.method == 'POST':
            try:
                negotiation_service.save_round(project_id, request.form)
                return redirect(url_for('procurement_negotiation', project_id=project_id))
            except Exception as exc:
                error = _form_error('谈判操作失败', exc)
        else:
            error = request.args.get('error', '')
        return render_template(
            'procurement/negotiation.html', view=negotiation_service.negotiation_view(project_id),
            error=error, money=_money,
        )

    @app.route('/procurement/projects/<int:project_id>/negotiation/plan', methods=['GET', 'POST'])
    def procurement_negotiation_plan(project_id):
        _project_or_404(project_id)
        try:
            defaults = project_document_service.negotiation_plan_defaults(project_id)
        except Exception as exc:
            return _error_redirect('procurement_project_detail', exc, exc_info=True, project_id=project_id)
        if request.method == 'POST':
            try:
                path = project_document_service.generate_negotiation_plan(project_id, request.form)
                return send_file(path, as_attachment=True, download_name=os.path.basename(path))
            except Exception as exc:
                error = _form_error('谈判预案生成失败', exc)
                plan = {**defaults['plan'], **{
                    key: request.form.get(key, defaults['plan'].get(key, ''))
                    for key in defaults['plan']
                }}
                return render_template(
                    'procurement/negotiation_plan.html', view=defaults,
                    plan=plan, error=error,
                ), 400
        return render_template(
            'procurement/negotiation_plan.html', view=defaults,
            plan=defaults['plan'], error=request.args.get('error', ''),
        )

    @app.route('/procurement/projects/<int:project_id>/negotiation/minutes')
    def procurement_negotiation_minutes(project_id):
        try:
            path = project_document_service.generate_negotiation_minutes(project_id)
        except Exception as exc:
            return _error_redirect('procurement_negotiation', exc, exc_info=True, project_id=project_id)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.route('/procurement/projects/<int:project_id>/negotiation/commitments')
    def procurement_final_commitments(project_id):
        try:
            path = project_document_service.export_final_commitments(project_id)
        except Exception as exc:
            return _error_redirect('procurement_negotiation', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/procurement/projects/<int:project_id>/to-contract', methods=['GET', 'POST'])
    def procurement_to_contract(project_id):
        project = _project_or_404(project_id)
        award = procurement_store.get_latest_award(project_id)
        if not award:
            return _error_redirect('procurement_award', '请先确认成交建议', project_id=project_id)
        templates = template_def.list_templates()
        if request.method == 'POST':
            template_filename = os.path.basename(request.form.get('template_filename', ''))
            try:
                data = award_service.prepare_editor_session(project_id, template_filename)
                sid = uuid.uuid4().hex
                helpers.save_session_data(sid, data)
                session['sid'] = sid
                return redirect(url_for('editor'))
            except Exception as exc:
                error = _form_error('成交转合同失败', exc)
                return render_template(
                    'procurement/to_contract.html', project=project, award=award,
                    templates=templates, error=error, money=_money,
                ), 400
        return render_template(
            'procurement/to_contract.html', project=project, award=award,
            templates=templates, error=request.args.get('error', ''), money=_money,
        )

    @app.route('/procurement/projects/<int:project_id>/direct-contract', methods=['GET', 'POST'])
    def procurement_direct_contract(project_id):
        project = _project_or_404(project_id)
        project['budget_amount'] = _money(project.get('budget_minor'))
        project['target_price'] = _money(project.get('target_price_minor'))
        templates = template_def.list_templates()
        if request.method == 'POST':
            template_filename = os.path.basename(request.form.get('template_filename', ''))
            try:
                data = procurement_project_service.prepare_direct_contract_session(project_id, template_filename)
                sid = uuid.uuid4().hex
                helpers.save_session_data(sid, data)
                session['sid'] = sid
                return redirect(url_for('editor'))
            except Exception as exc:
                error = _form_error('直接生成合同失败', exc)
                return render_template(
                    'procurement/direct_contract.html', project=project,
                    templates=templates, error=error,
                ), 400
        return render_template(
            'procurement/direct_contract.html', project=project,
            templates=templates, error=request.args.get('error', ''),
        )
