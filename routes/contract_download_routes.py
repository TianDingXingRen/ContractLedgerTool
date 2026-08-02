"""Contract document download routes."""

from __future__ import annotations

import os

from flask import send_file

import ledger_store
from runtime.flask_paths import current_runtime_paths
from utils.security import path_within


def _contract_file_context(contract_id):
    contract = ledger_store.get_contract(contract_id)
    if not contract:
        return None, ('合同记录不存在', 404)
    docx_path = contract.get('docx_path') or ''
    output_dir = str(current_runtime_paths().output_dir)
    if (
        not docx_path
        or not path_within(output_dir, docx_path)
        or not os.path.exists(docx_path)
    ):
        return None, ('合同文件不存在，可能已被移动或删除', 404)
    return (contract, docx_path), None


def register_contract_download_routes(bp):
    @bp.route('/contracts/<int:contract_id>/download')
    def contract_download(contract_id):
        context, error = _contract_file_context(contract_id)
        if error:
            return error
        contract, docx_path = context
        base = contract.get('contract_no') or f'contract_{contract_id}'
        return send_file(
            docx_path,
            as_attachment=True,
            download_name=f'{base}.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
