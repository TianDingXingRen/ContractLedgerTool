"""Procurement document generation, archive, and download routes."""

from __future__ import annotations

import os

from flask import abort, request, send_file

import procurement_store
from services import procurement_file_service, project_document_service, quote_service


def register_document_routes(bp, error_redirect):
    """Attach document-focused routes to the procurement blueprint."""

    @bp.route('/procurement/projects/<int:project_id>/quote-template/<int:supplier_id>')
    def procurement_quote_template(project_id, supplier_id):
        try:
            path = quote_service.generate_quote_template(project_id, supplier_id)
        except Exception as exc:
            return error_redirect(
                'procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @bp.route('/procurement/projects/<int:project_id>/inquiry')
    def procurement_inquiry_document(project_id):
        try:
            path = project_document_service.generate_inquiry_letter(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @bp.route('/procurement/projects/<int:project_id>/clarifications/document')
    def procurement_clarification_document(project_id):
        try:
            path = project_document_service.generate_clarification_letter(
                project_id, request.args.get('supplier_id', type=int)
            )
        except Exception as exc:
            return error_redirect(
                'procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @bp.route('/procurement/projects/<int:project_id>/award/document')
    def procurement_award_document(project_id):
        try:
            path = project_document_service.generate_award_recommendation(project_id)
        except Exception as exc:
            return error_redirect('procurement_award', exc, exc_info=True, project_id=project_id)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @bp.route('/procurement/files/<int:file_id>/download')
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

    @bp.route('/procurement/projects/<int:project_id>/erp-oa-summary')
    def procurement_erp_oa_summary(project_id):
        try:
            path = project_document_service.generate_erp_oa_summary(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @bp.route('/procurement/projects/<int:project_id>/archive')
    def procurement_project_archive(project_id):
        try:
            path = project_document_service.generate_project_archive(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/zip',
        )
