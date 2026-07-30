"""Consistent one-connection read model for the home dashboard."""

from __future__ import annotations

from datetime import date

import ledger_store
import template_def
from services import workbench_service
from utils.generation_utils import next_month_ym
from utils.labels import CONTRACT_STATUS_LABELS


def build_dashboard_snapshot(today=None):
    today = today or date.today()
    with ledger_store.read_snapshot():
        next_year, next_month_number = next_month_ym(today)
        return {
            'contract_stats': ledger_store.get_contract_stats(),
            'payment_stats': ledger_store.get_payment_stats(),
            'this_month': ledger_store.get_monthly_payments(today.year, today.month),
            'next_month': ledger_store.get_monthly_payments(next_year, next_month_number),
            'due_soon': ledger_store.get_due_soon_payments(days=7, limit=50),
            'expiring_contracts': ledger_store.get_expiring_contracts(days=30, limit=50),
            'recent_contracts': ledger_store.get_recent_contracts(5),
            'project_progress': ledger_store.get_project_progress_stats(),
            'recent_templates': template_def.list_templates()[:5],
            'workbench': workbench_service.build_workbench(today=today),
            'status_labels': CONTRACT_STATUS_LABELS,
            'today': today,
        }
