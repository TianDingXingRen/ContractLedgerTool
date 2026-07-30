"""Generate payment artifacts outside the HTTP adapter."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import ledger_store
import xlsx_exporter
from runtime.flask_paths import current_runtime_paths


PAYMENT_REPORT_MIMETYPE = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)


@dataclass(frozen=True)
class GeneratedPaymentReport:
    path: str
    download_name: str
    mimetype: str = PAYMENT_REPORT_MIMETYPE


def generate_monthly_payment_report(report_month):
    report = ledger_store.build_monthly_payment_report(report_month)
    month_token = report['report_month'].replace('-', '')
    filename = (
        f'monthly_payment_plan_{month_token}_{uuid.uuid4().hex[:8]}.xlsx'
    )
    output_path = os.path.join(
        str(current_runtime_paths().output_dir), filename
    )
    xlsx_exporter.export_monthly_payment_plan_report(output_path, report)
    year, month = report['report_month'].split('-')
    return GeneratedPaymentReport(
        path=output_path,
        download_name=f'{year}年{int(month)}月合同付款计划.xlsx',
    )
