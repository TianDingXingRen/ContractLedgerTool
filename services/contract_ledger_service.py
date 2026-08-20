"""Contract ledger queries, exports, and lifecycle commands."""

from __future__ import annotations

import os
import uuid
from datetime import date

import ledger_store
import xlsx_exporter


VALID_CONTRACT_STATUSES = {
    'draft',
    'signed',
    'active',
    'completed',
    'void',
}


def ledger_view(*, query='', status='', view_mode='list', page=1):
    result = ledger_store.list_contracts(
        q=query,
        status=status,
        page=page,
    )
    project_groups = (
        ledger_store.list_project_grouped_contracts(
            q=query,
            status=status,
        )
        if view_mode == 'project'
        else []
    )
    return {
        'contracts': result['rows'],
        'contract_ids': [row['id'] for row in result['rows']],
        'project_groups': project_groups,
        'view_mode': view_mode,
        'q': query,
        'status': status,
        'page': result['page'],
        'pages': result['pages'],
        'total': result['total'],
    }


def trash_view(page=1):
    result = ledger_store.list_contracts(
        page=page,
        per_page=20,
        deleted_only=True,
    )
    return {
        'contracts': result['rows'],
        'contract_ids': [row['id'] for row in result['rows']],
        'q': '',
        'status': '',
        'view_mode': 'list',
        'page': result['page'],
        'pages': result['pages'],
        'total': result['total'],
        'trash_mode': True,
    }


def export_ledger(output_dir, *, query='', status='', today=None):
    today = today or date.today()
    filename = (
        f'contracts_{today.strftime("%Y%m%d")}_'
        f'{uuid.uuid4().hex[:8]}.xlsx'
    )
    output_path = os.path.join(str(output_dir), filename)
    contracts = ledger_store.iter_contracts(
        q=query,
        status=status,
        batch_size=500,
    )
    xlsx_exporter.export_contracts(
        output_path,
        contracts,
        title='合同台账',
        streaming=True,
    )
    return output_path, f'合同台账_{today.strftime("%Y%m%d")}.xlsx'


def contract_exists(contract_id):
    return bool(ledger_store.get_contract(contract_id))


def update_contract(contract_id, update, *, expected_revision):
    return ledger_store.update_contract(
        contract_id,
        update,
        expected_revision=expected_revision,
    )


def batch_delete(contract_ids):
    return ledger_store.batch_delete_contracts(contract_ids)


def batch_update_status(contract_ids, status):
    return ledger_store.batch_update_status(contract_ids, status)


def soft_delete(contract_id):
    return ledger_store.soft_delete_contract(contract_id)


def restore(contract_id):
    return ledger_store.restore_contract(contract_id)


def permanently_delete(contract_id):
    return ledger_store.permanently_delete_contract(contract_id)
