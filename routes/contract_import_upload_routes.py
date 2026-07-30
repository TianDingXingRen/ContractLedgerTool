"""HTTP adapters for starting an external contract import."""

from __future__ import annotations

import os

from flask import (
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from services import contract_import_workflow


def register_contract_import_upload_routes(bp):
    @bp.get('/contracts/import')
    def contract_import():
        return render_template(
            'contract_import.html',
            error=request.args.get('error', ''),
        )

    @bp.post('/contracts/import/preview')
    def contract_import_preview():
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return render_template(
                'contract_import.html',
                error='请选择 DOCX 合同文件',
            ), 400
        original_name = os.path.basename(upload.filename)[:255]
        if os.path.splitext(original_name)[1].lower() != '.docx':
            return render_template(
                'contract_import.html',
                error='仅支持 .docx 格式',
            ), 400

        previous_sid = session.get('contract_import_sid')
        if previous_sid:
            session.pop('contract_import_sid', None)
        try:
            sid = contract_import_workflow.start_import_preview(
                upload.stream,
                original_name,
                previous_sid=previous_sid,
                importer=current_app.extensions[
                    'contract_tool'
                ].contract_import,
            )
        except contract_import_workflow.ImportPreviewRejected as exc:
            return render_template(
                'contract_import.html',
                error=str(exc),
                duplicate_contract=exc.duplicate_contract,
            ), exc.status

        session['contract_import_sid'] = sid
        return redirect(
            url_for(
                'contract_import.contract_import_review', sid=sid
            )
        )
