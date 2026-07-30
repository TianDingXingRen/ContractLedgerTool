"""HTTP adapters for procurement items and candidate suppliers."""

from __future__ import annotations

import os

from flask import (
    abort,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from routes.procurement_route_support import (
    error_redirect,
    form_error,
    project_or_404,
    project_section_url,
)
from services import (
    procurement_project_service,
    project_document_service,
    quote_service,
)


XLSX_MIMETYPE = (
    'application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.sheet'
)


def procurement_item_add(project_id):
    try:
        procurement_project_service.add_item(
            project_id,
            request.form,
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_project_detail',
            exc,
            exc_info=True,
            project_id=project_id,
        )
    return redirect(project_section_url(project_id, 'items'))


def procurement_items_bulk(project_id):
    project = project_or_404(project_id)
    if request.method == 'POST':
        try:
            upload = request.files.get('file')
            if upload and upload.filename:
                procurement_project_service.add_items_from_excel(
                    project_id,
                    upload,
                )
            else:
                procurement_project_service.add_items_from_paste(
                    project_id,
                    request.form.get('pasted_rows', ''),
                )
            return redirect(
                url_for(
                    'procurement.procurement_project_detail',
                    project_id=project_id,
                )
            )
        except Exception as exc:
            return render_template(
                'procurement/items_bulk.html',
                project=project,
                pasted_rows=request.form.get(
                    'pasted_rows',
                    '',
                ),
                error=form_error(
                    '采购明细批量导入失败',
                    exc,
                ),
            ), 400
    return render_template(
        'procurement/items_bulk.html',
        project=project,
        pasted_rows='',
        error='',
    )


def procurement_items_export(project_id):
    try:
        path = project_document_service.export_project_items(
            project_id
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_project_detail',
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


def procurement_item_delete(project_id, item_id):
    try:
        procurement_project_service.delete_item(
            project_id,
            item_id,
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


def procurement_item_edit(project_id, item_id):
    project_or_404(project_id)
    item = procurement_project_service.get_project_item(
        project_id,
        item_id,
    )
    if not item:
        abort(404, description='采购明细不存在')
    if request.method == 'POST':
        try:
            procurement_project_service.update_item(
                project_id,
                item_id,
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
                'procurement/item_form.html',
                project_id=project_id,
                item={**item, **request.form},
                error=form_error(
                    '采购明细更新失败',
                    exc,
                ),
            ), 400
    return render_template(
        'procurement/item_form.html',
        project_id=project_id,
        item=item,
        error='',
    )


def procurement_supplier_add(project_id):
    try:
        procurement_project_service.add_supplier(
            project_id,
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
        project_section_url(project_id, 'suppliers')
    )


def procurement_quote_template_selected(project_id):
    supplier_id = request.form.get(
        'supplier_id',
        type=int,
    )
    if not supplier_id:
        return error_redirect(
            'procurement.procurement_quote_import',
            '请选择候选供应商后下载模板',
            project_id=project_id,
        )
    try:
        path = quote_service.generate_quote_template(
            project_id,
            supplier_id,
        )
    except Exception as exc:
        return error_redirect(
            'procurement.procurement_quote_import',
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


def procurement_supplier_delete(project_id, supplier_id):
    try:
        procurement_project_service.delete_supplier(
            project_id,
            supplier_id,
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


def procurement_supplier_edit(project_id, supplier_id):
    project_or_404(project_id)
    supplier = procurement_project_service.get_supplier(
        project_id,
        supplier_id,
    )
    if not supplier:
        abort(404, description='候选供应商不存在')
    if request.method == 'POST':
        try:
            procurement_project_service.update_supplier(
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
                'procurement/supplier_form.html',
                project_id=project_id,
                supplier={**supplier, **request.form},
                error=form_error(
                    '候选供应商更新失败',
                    exc,
                ),
            ), 400
    return render_template(
        'procurement/supplier_form.html',
        project_id=project_id,
        supplier=supplier,
        error='',
    )


def register_procurement_item_supplier_routes(bp):
    routes = (
        (
            '/procurement/projects/<int:project_id>/items',
            procurement_item_add,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/items/bulk',
            procurement_items_bulk,
            ['GET', 'POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/items/export',
            procurement_items_export,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/items/'
            '<int:item_id>/delete',
            procurement_item_delete,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/items/'
            '<int:item_id>/edit',
            procurement_item_edit,
            ['GET', 'POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/suppliers',
            procurement_supplier_add,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/quote-template',
            procurement_quote_template_selected,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/suppliers/'
            '<int:supplier_id>/delete',
            procurement_supplier_delete,
            ['POST'],
        ),
        (
            '/procurement/projects/<int:project_id>/suppliers/'
            '<int:supplier_id>/edit',
            procurement_supplier_edit,
            ['GET', 'POST'],
        ),
    )
    for rule, view_func, methods in routes:
        bp.add_url_rule(
            rule,
            view_func=view_func,
            methods=methods,
        )
