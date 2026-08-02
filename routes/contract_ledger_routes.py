"""Contract ledger, export, update, and trash HTTP routes."""

from __future__ import annotations

import json

from flask import redirect, render_template, request, send_file, url_for

from routes import contract_batch_support
from routes.workspace_navigation import contract_detail_location
from runtime.flask_paths import current_runtime_paths
from services import contract_ledger_service
from utils.errors import safe_error
from utils.logger import get_logger
from utils.security import MAX_BATCH_CONTRACTS


def _positive_page():
    try:
        return max(1, int(request.args.get('page', 1)))
    except ValueError:
        return 1


def _contract_ids():
    try:
        payload = json.loads(request.form.get('ids', '[]'))
        if not isinstance(payload, list):
            raise ValueError
        contract_ids = [
            int(value)
            for value in payload
        ]
        if any(contract_id <= 0 for contract_id in contract_ids):
            raise ValueError
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError('无效的 ID 列表') from exc
    if len(contract_ids) > MAX_BATCH_CONTRACTS:
        raise OverflowError(
            f'单次不能超过 {MAX_BATCH_CONTRACTS} 条记录'
        )
    return contract_ids


def contract_ledger():
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    view_mode = request.args.get('view', 'list').strip()
    if view_mode not in {'list', 'project'}:
        view_mode = 'list'
    model = contract_ledger_service.ledger_view(
        query=query,
        status=status,
        view_mode=view_mode,
        page=_positive_page(),
    )
    return render_template('contracts.html', **model)


def contract_export():
    output_path, download_name = contract_ledger_service.export_ledger(
        current_runtime_paths().output_dir,
        query=request.form.get('q', '').strip(),
        status=request.form.get('status', '').strip(),
    )
    return send_file(
        output_path,
        as_attachment=True,
        download_name=download_name,
        mimetype=(
            'application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet'
        ),
    )


def contract_batch_delete():
    try:
        contract_ids = _contract_ids()
    except ValueError as exc:
        return str(exc), 400
    except OverflowError as exc:
        return str(exc), 400
    count = contract_ledger_service.batch_delete(contract_ids)
    get_logger().info(
        'Batch deleted %d contracts: %s',
        count,
        contract_ids,
    )
    return redirect(url_for('contracts.contract_ledger'))


def contract_batch_status():
    new_status = request.form.get('status', '').strip()
    if new_status not in contract_ledger_service.VALID_CONTRACT_STATUSES:
        return '无效的状态值', 400
    try:
        contract_ids = _contract_ids()
    except ValueError as exc:
        return str(exc), 400
    except OverflowError as exc:
        return str(exc), 400
    count = contract_ledger_service.batch_update_status(
        contract_ids,
        new_status,
    )
    get_logger().info(
        'Batch updated %d contracts',
        count,
    )
    return redirect(url_for('contracts.contract_ledger'))


def contract_trash():
    model = contract_ledger_service.trash_view(_positive_page())
    return render_template('contracts.html', **model)


def contract_soft_delete(contract_id):
    count = contract_ledger_service.soft_delete(contract_id)
    if count == 0:
        return '合同不存在或已在回收站中', 404
    get_logger().info('Soft deleted contract %d', contract_id)
    return redirect(url_for('contracts.contract_ledger'))


def contract_restore(contract_id):
    count = contract_ledger_service.restore(contract_id)
    if count == 0:
        return '合同不在回收站中', 404
    get_logger().info('Restored contract %d from trash', contract_id)
    return redirect(url_for('contracts.contract_trash'))


def contract_permanent_delete(contract_id):
    try:
        count = contract_ledger_service.permanently_delete(contract_id)
    except ValueError as exc:
        return redirect(
            url_for(
                'contracts.contract_detail',
                contract_id=contract_id,
                error=str(exc),
            )
        )
    if count == 0:
        return '合同不在回收站中或无法删除', 404
    get_logger().info('Permanently deleted contract %d', contract_id)
    return redirect(url_for('contracts.contract_trash'))


def contract_update(contract_id):
    if not contract_ledger_service.contract_exists(contract_id):
        return '合同记录不存在', 404
    new_status = request.form.get('status', 'draft').strip() or 'draft'
    if new_status not in contract_ledger_service.VALID_CONTRACT_STATUSES:
        return '无效的状态值', 400
    try:
        update = contract_batch_support.parse_contract_update(
            request.form,
            new_status,
        )
        contract_ledger_service.update_contract(contract_id, update)
    except ValueError as exc:
        return safe_error(exc, '合同更新失败')
    return redirect(
        contract_detail_location(
            contract_id,
            request.form,
            default_tab='overview',
        )
    )


def register_contract_ledger_routes(bp):
    bp.add_url_rule(
        '/contracts',
        endpoint='contract_ledger',
        view_func=contract_ledger,
    )
    bp.add_url_rule(
        '/contracts/export',
        endpoint='contract_export',
        view_func=contract_export,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/contracts/batch-delete',
        endpoint='contract_batch_delete',
        view_func=contract_batch_delete,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/contracts/batch-status',
        endpoint='contract_batch_status',
        view_func=contract_batch_status,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/contracts/trash',
        endpoint='contract_trash',
        view_func=contract_trash,
    )
    bp.add_url_rule(
        '/contracts/<int:contract_id>/soft-delete',
        endpoint='contract_soft_delete',
        view_func=contract_soft_delete,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/contracts/<int:contract_id>/restore',
        endpoint='contract_restore',
        view_func=contract_restore,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/contracts/<int:contract_id>/permanent-delete',
        endpoint='contract_permanent_delete',
        view_func=contract_permanent_delete,
        methods=['POST'],
    )
    bp.add_url_rule(
        '/contracts/<int:contract_id>/update',
        endpoint='contract_update',
        view_func=contract_update,
        methods=['POST'],
    )
