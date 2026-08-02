"""HTTP adapters for payment report downloads."""

from __future__ import annotations

from flask import request, send_file

from services.payment_exports import generate_monthly_payment_report
from utils.generation_utils import next_month_range


def _send_monthly_report(report_month):
    try:
        artifact = generate_monthly_payment_report(report_month)
    except ValueError as exc:
        return str(exc), 400
    return send_file(
        artifact.path,
        as_attachment=True,
        download_name=artifact.download_name,
        mimetype=artifact.mimetype,
    )


def register_payment_export_routes(bp):
    @bp.post('/payment-plans/export')
    def export_payment_plans():
        return _send_monthly_report(
            request.form.get('report_month', '')
        )

    @bp.post('/payment-plans/export-next-month')
    def export_next_month_payments():
        start, _end = next_month_range()
        return _send_monthly_report(start[:7])
