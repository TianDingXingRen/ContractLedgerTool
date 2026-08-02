"""HTTP adapters for standard and mapped supplier quote imports."""

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
    has_allowed_extension,
    money,
    project_or_404,
)
from services import (
    procurement_project_service,
    quote_mapping_service,
    quote_service,
)


STANDARD_QUOTE_EXTENSIONS = {'.xlsx'}
MAPPING_QUOTE_EXTENSIONS = {'.xlsx', '.docx', '.pdf'}
PDF_EXTENSIONS = {'.pdf'}


def _quote_import_page(
    project,
    suppliers,
    error,
    status=200,
):
    return render_template(
        'procurement/quote_import.html',
        project=project,
        suppliers=suppliers,
        error=error,
    ), status


def _mapping_upload_page(
    project,
    suppliers,
    error,
    status=200,
):
    return render_template(
        'procurement/quote_mapping_upload.html',
        project=project,
        suppliers=suppliers,
        error=error,
    ), status


def procurement_quote_import(project_id):
    project = project_or_404(project_id)
    suppliers = procurement_project_service.list_suppliers(
        project_id
    )
    if request.method == 'POST':
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return _quote_import_page(
                project,
                suppliers,
                '请选择报价 Excel 文件',
                400,
            )
        if not has_allowed_extension(
            upload.filename,
            STANDARD_QUOTE_EXTENSIONS,
        ):
            return _quote_import_page(
                project,
                suppliers,
                '标准报价仅支持 .xlsx 格式',
                400,
            )
        try:
            supplier_id = int(
                request.form.get('supplier_id', 0)
            )
            quote_round = int(
                request.form.get('quote_round', 1)
            )
            job_id = quote_service.create_import_job(
                project_id,
                supplier_id,
                quote_round,
                upload,
            )
            return redirect(
                url_for(
                    'procurement.procurement_quote_preview',
                    job_id=job_id,
                )
            )
        except Exception as exc:
            return _quote_import_page(
                project,
                suppliers,
                form_error('报价导入失败', exc),
                400,
            )
    return _quote_import_page(
        project,
        suppliers,
        request.args.get('error', ''),
    )


def procurement_quote_pdf_upload(project_id):
    project = project_or_404(project_id)
    suppliers = procurement_project_service.list_suppliers(
        project_id
    )
    upload = request.files.get('file')
    if not upload or not upload.filename:
        return _quote_import_page(
            project,
            suppliers,
            '请选择 PDF 报价单',
            400,
        )
    if not has_allowed_extension(
        upload.filename,
        PDF_EXTENSIONS,
    ):
        return _quote_import_page(
            project,
            suppliers,
            'PDF 报价单仅支持 .pdf 格式',
            400,
        )
    try:
        quote_service.save_quote_pdf_attachment(
            project_id,
            int(request.form.get('supplier_id', 0)),
            int(request.form.get('quote_round', 1)),
            upload,
        )
    except Exception as exc:
        return _quote_import_page(
            project,
            suppliers,
            form_error('PDF 报价单上传失败', exc),
            400,
        )
    return redirect(
        url_for(
            'procurement.procurement_project_detail',
            project_id=project_id,
        )
    )


def procurement_quote_mapping_upload(project_id):
    project = project_or_404(project_id)
    suppliers = procurement_project_service.list_suppliers(
        project_id
    )
    if request.method == 'POST':
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return _mapping_upload_page(
                project,
                suppliers,
                '请选择报价文件',
                400,
            )
        if not has_allowed_extension(
            upload.filename,
            MAPPING_QUOTE_EXTENSIONS,
        ):
            return _mapping_upload_page(
                project,
                suppliers,
                '非标准报价仅支持 .xlsx、.docx 或 .pdf',
                400,
            )
        try:
            job_id = quote_mapping_service.create_mapping_job(
                project_id,
                int(request.form.get('supplier_id', 0)),
                int(request.form.get('quote_round', 1)),
                upload,
            )
            return redirect(
                url_for(
                    'procurement.procurement_quote_mapping',
                    job_id=job_id,
                )
            )
        except Exception as exc:
            return _mapping_upload_page(
                project,
                suppliers,
                form_error(
                    '报价映射任务创建失败',
                    exc,
                ),
                400,
            )
    return _mapping_upload_page(
        project,
        suppliers,
        request.args.get('error', ''),
    )


def procurement_quote_mapping(job_id):
    job = quote_mapping_service.get_mapping_job(job_id)
    if not job:
        abort(404, description='字段映射任务不存在')
    if request.method == 'POST':
        try:
            import_job_id = (
                quote_mapping_service.map_to_import_job(
                    job_id,
                    request.form,
                )
            )
            return redirect(
                url_for(
                    'procurement.procurement_quote_preview',
                    job_id=import_job_id,
                )
            )
        except Exception as exc:
            error = form_error(
                f'报价映射失败 (job {job_id})',
                exc,
            )
    else:
        error = request.args.get('error', '')
    selected_name = (
        request.args.get('table')
        or job['source']['tables'][0]['name']
    )
    selected = next(
        (
            table
            for table in job['source']['tables']
            if table['name'] == selected_name
        ),
        job['source']['tables'][0],
    )
    headers = (
        selected['rows'][0]
        if selected['rows']
        else []
    )
    return render_template(
        'procurement/quote_mapping.html',
        job=job,
        selected=selected,
        headers=headers,
        mapping_fields=quote_mapping_service.MAPPING_FIELDS,
        error=error,
    )


def procurement_quote_preview(job_id):
    job = quote_service.get_import_job(job_id)
    if not job:
        abort(404, description='报价导入任务不存在')
    return render_template(
        'procurement/quote_preview.html',
        job=job,
        money=money,
    )


def procurement_quote_confirm(job_id):
    job = quote_service.get_import_job(job_id)
    if not job:
        abort(404, description='报价导入任务不存在')
    try:
        quote_service.confirm_import(job_id)
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_quote_import',
            exc,
            exc_info=True,
            project_id=job['project_id'],
        )
    return redirect(
        url_for(
            'procurement.procurement_project_detail',
            project_id=job['project_id'],
        )
    )


def register_procurement_import_routes(bp):
    routes = (
        (
            '/procurement/projects/<int:project_id>/quotes/import',
            procurement_quote_import,
            ['GET', 'POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/quotes/pdf',
            procurement_quote_pdf_upload,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/quotes/map',
            procurement_quote_mapping_upload,
            ['GET', 'POST'],
        ),
        (
            '/procurement/quote-mappings/<int:job_id>',
            procurement_quote_mapping,
            ['GET', 'POST'],
        ),
        (
            '/procurement/quote-imports/<int:job_id>',
            procurement_quote_preview,
            ['GET'],
        ),
        (
            '/procurement/quote-imports/<int:job_id>/confirm',
            procurement_quote_confirm,
            ['POST'],
        ),
    )
    for rule, view_func, methods in routes:
        bp.add_url_rule(
            rule,
            view_func=view_func,
            methods=methods,
        )
