"""Procurement document generation, archive, and download routes."""

from __future__ import annotations

import os

from flask import abort, request, send_file

from services import procurement_file_service, project_document_service, quote_service


DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _artifact_mimetype(path):
    return {
        '.docx': DOCX_MIME,
        '.xlsx': XLSX_MIME,
        '.pdf': 'application/pdf',
        '.zip': 'application/zip',
    }.get(os.path.splitext(os.fspath(path))[1].lower(), 'application/octet-stream')


def register_document_routes(bp, error_redirect):
    """Attach document-focused routes to the procurement blueprint."""
    @bp.route(
        '/procurement/projects/<int:project_id>/quote-template/<int:supplier_id>',
        methods=['POST'],
    )
    def procurement_quote_template(project_id, supplier_id):
        try:
            path = quote_service.generate_quote_template(project_id, supplier_id)
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype=XLSX_MIME,
        )

    @bp.route('/procurement/projects/<int:project_id>/inquiry', methods=['POST'])
    def procurement_inquiry_document(project_id):
        try:
            path = project_document_service.generate_inquiry_letter(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype=DOCX_MIME,
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/clarifications/document',
        methods=['POST'],
    )
    def procurement_clarification_document(project_id):
        try:
            path = project_document_service.generate_clarification_letter(
                project_id, request.form.get('supplier_id', type=int)
            )
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype=DOCX_MIME,
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/award/document',
        methods=['POST'],
    )
    def procurement_award_document(project_id):
        try:
            path = project_document_service.generate_award_recommendation(project_id)
        except Exception as exc:
            return error_redirect('procurement.procurement_award', exc, exc_info=True, project_id=project_id)
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype=DOCX_MIME,
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/negotiation/minutes',
        methods=['POST'],
    )
    def procurement_negotiation_minutes(project_id):
        try:
            path = project_document_service.generate_negotiation_minutes(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_negotiation',
                exc,
                exc_info=True,
                project_id=project_id,
            )
        return send_file(
            path,
            as_attachment=True,
            download_name=os.path.basename(path),
            mimetype=DOCX_MIME,
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/negotiation/commitments',
        methods=['POST'],
    )
    def procurement_final_commitments(project_id):
        try:
            path = project_document_service.export_final_commitments(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_negotiation',
                exc,
                exc_info=True,
                project_id=project_id,
            )
        return send_file(
            path,
            as_attachment=True,
            download_name=os.path.basename(path),
            mimetype=XLSX_MIME,
        )

    @bp.route('/procurement/files/<int:file_id>/download')
    def procurement_file_download(file_id):
        try:
            artifact = procurement_file_service.resolve_download(
                file_id
            )
        except ValueError as exc:
            abort(400, description=str(exc))
        except FileNotFoundError as exc:
            abort(404, description=str(exc))
        path = artifact['path']
        return send_file(
            path, as_attachment=True,
            download_name=artifact['download_name'],
            mimetype=_artifact_mimetype(path),
        )

    @bp.route(
        '/procurement/projects/<int:project_id>/erp-oa-summary',
        methods=['POST'],
    )
    def procurement_erp_oa_summary(project_id):
        try:
            path = project_document_service.generate_erp_oa_summary(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype=XLSX_MIME,
        )

    @bp.route('/procurement/projects/<int:project_id>/archive', methods=['POST'])
    def procurement_project_archive(project_id):
        try:
            path = project_document_service.generate_project_archive(project_id)
        except Exception as exc:
            return error_redirect(
                'procurement.procurement_project_detail', exc, exc_info=True, project_id=project_id,
            )
        return send_file(
            path, as_attachment=True, download_name=os.path.basename(path),
            mimetype='application/zip',
        )
