"""Contract product baselines and production notice routes."""

from __future__ import annotations

import sqlite3
from datetime import date

from flask import redirect, render_template, request, url_for

import ledger_store
from routes.legacy_blueprint import LegacyEndpointBlueprint
from utils import helpers


MAX_ITEM_ROWS = 500


def _normalized_date(value, label, *, required=False):
    raw = str(value or '').strip()
    if not raw and not required:
        return ''
    normalized = helpers.normalize_date(raw)
    if not normalized:
        raise ValueError(f'{label}格式无效，请使用 YYYY-MM-DD')
    return normalized


def _contract_item_rows(form):
    try:
        count = min(MAX_ITEM_ROWS, max(0, int(form.get('item_count', 0))))
    except (TypeError, ValueError):
        raise ValueError('合同产品行数无效')
    rows = []
    for index in range(count):
        rows.append({
            'id': form.get(f'item_{index}_id', ''),
            'line_no': form.get(f'item_{index}_line_no', index + 1),
            'item_code': form.get(f'item_{index}_item_code', ''),
            'item_name': form.get(f'item_{index}_item_name', ''),
            'spec_model': form.get(f'item_{index}_spec_model', ''),
            'drawing_no': form.get(f'item_{index}_drawing_no', ''),
            'contracted_qty': form.get(f'item_{index}_contracted_qty', ''),
            'unit': form.get(f'item_{index}_unit', '个'),
            'unit_price': form.get(f'item_{index}_unit_price', ''),
            'serial_start': form.get(f'item_{index}_serial_start', ''),
            'serial_end': form.get(f'item_{index}_serial_end', ''),
            'delete': form.get(f'item_{index}_delete') == '1',
        })
    return rows


def _notice_rows(form):
    try:
        count = min(MAX_ITEM_ROWS, max(0, int(form.get('item_count', 0))))
    except (TypeError, ValueError):
        raise ValueError('投产通知产品行数无效')
    rows = []
    for index in range(count):
        delivery_raw = str(form.get(f'item_{index}_required_delivery_date', '') or '').strip()
        rows.append({
            'contract_item_id': form.get(f'item_{index}_contract_item_id', ''),
            'notice_qty': form.get(f'item_{index}_notice_qty', ''),
            'serial_start': form.get(f'item_{index}_serial_start', ''),
            'serial_end': form.get(f'item_{index}_serial_end', ''),
            'required_delivery_date': (
                _normalized_date(delivery_raw, '要求交付日期') if delivery_raw else ''
            ),
            'remark': form.get(f'item_{index}_remark', ''),
        })
    return rows


def _notice_header(form):
    notice_date_raw = str(form.get('notice_date', '') or '').strip()
    return {
        'notice_no': form.get('notice_no', ''),
        'notice_date': (
            _normalized_date(notice_date_raw, '通知日期') if notice_date_raw else ''
        ),
        'supplier_name': form.get('supplier_name', ''),
        'project_name': form.get('project_name', ''),
        'remark': form.get('remark', ''),
        'operator': form.get('operator', ''),
    }


def _notice_form_context(contract, notice=None, error=''):
    contract_items = ledger_store.list_contract_items(contract['id'])
    values = {}
    if notice:
        values = {item['contract_item_id']: item for item in notice.get('items', [])}
    return {
        'contract': contract,
        'notice': notice,
        'contract_items': contract_items,
        'notice_item_values': values,
        'today': date.today().strftime('%Y-%m-%d'),
        'error': error,
    }


def _register_contract_item_routes(bp):
    @bp.route('/contracts/<int:contract_id>/items', methods=['GET', 'POST'])
    def contract_items_page(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        error = request.args.get('error', '')
        if request.method == 'POST':
            try:
                ledger_store.save_contract_items(
                    contract_id, _contract_item_rows(request.form),
                    operator=request.form.get('operator', '').strip(),
                )
                return redirect(url_for('contract_items_page', contract_id=contract_id))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc) if isinstance(exc, ValueError) else '合同产品行号重复'
        items = ledger_store.list_contract_items(contract_id)
        return render_template(
            'contract_items.html', contract=contract, items=items, error=error,
            message=request.args.get('message', ''),
            item_history=ledger_store.list_contract_item_history(contract_id),
        ), 400 if error and request.method == 'POST' else 200

    @bp.route('/contracts/<int:contract_id>/items/sync-procurement', methods=['POST'])
    def contract_items_sync_procurement(contract_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        try:
            report = ledger_store.sync_contract_items_from_procurement(contract_id)
            detail = f"新增 {report['created']} 条，更新 {report['updated']} 条"
            if report['issues']:
                detail += '；需人工处理：' + '；'.join(report['issues'][:3])
            return redirect(url_for(
                'contract_items_page', contract_id=contract_id, message=detail
            ))
        except ValueError as exc:
            return redirect(url_for(
                'contract_items_page', contract_id=contract_id, error=str(exc)
            ))

def _register_notice_routes(bp):
    @bp.route('/production-notices')
    def production_notice_list():
        status = request.args.get('status', '').strip()
        contract_id = request.args.get('contract_id', type=int)
        page = max(1, request.args.get('page', 1, type=int) or 1)
        if status not in {'', 'draft', 'issued', 'acknowledged', 'closed', 'cancelled'}:
            status = ''
        result = ledger_store.list_production_notices(
            contract_id=contract_id, status=status, page=page
        )
        return render_template(
            'production_notice_list.html',
            notices=result['rows'],
            status=status,
            contract_id=contract_id,
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
        )

    @bp.route('/contracts/<int:contract_id>/production-notices/new', methods=['GET', 'POST'])
    def production_notice_new(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        if not ledger_store.list_contract_items(contract_id):
            return redirect(url_for(
                'contract_items_page', contract_id=contract_id,
                error='请先维护合同产品基线，再创建投产通知',
            ))
        if request.method == 'POST':
            try:
                notice_id = ledger_store.create_production_notice(
                    contract_id, _notice_header(request.form), _notice_rows(request.form)
                )
                return redirect(url_for('production_notice_detail', notice_id=notice_id))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc) if isinstance(exc, ValueError) else '投产通知编号已存在'
                return render_template(
                    'production_notice_form.html',
                    **_notice_form_context(contract, error=error),
                ), 400
        return render_template(
            'production_notice_form.html', **_notice_form_context(contract)
        )

    @bp.route('/production-notices/<int:notice_id>')
    def production_notice_detail(notice_id):
        notice = ledger_store.get_production_notice(notice_id)
        if not notice:
            return '投产通知不存在', 404
        return render_template(
            'production_notice_detail.html',
            notice=notice,
            error=request.args.get('error', ''),
            message=request.args.get('message', ''),
        )

    @bp.route('/production-notices/<int:notice_id>/edit', methods=['GET', 'POST'])
    def production_notice_edit(notice_id):
        notice = ledger_store.get_production_notice(notice_id)
        if not notice:
            return '投产通知不存在', 404
        if notice['status'] != 'draft':
            return redirect(url_for(
                'production_notice_detail', notice_id=notice_id,
                error='正式发出后的投产通知已锁定，不能直接修改',
            ))
        contract = ledger_store.get_contract(notice['contract_id'])
        if request.method == 'POST':
            try:
                ledger_store.save_production_notice_draft(
                    notice_id, _notice_header(request.form), _notice_rows(request.form)
                )
                return redirect(url_for('production_notice_detail', notice_id=notice_id))
            except (ValueError, sqlite3.IntegrityError) as exc:
                refreshed = ledger_store.get_production_notice(notice_id)
                error = str(exc) if isinstance(exc, ValueError) else '投产通知编号已存在'
                return render_template(
                    'production_notice_form.html',
                    **_notice_form_context(contract, refreshed, error),
                ), 400
        return render_template(
            'production_notice_form.html',
            **_notice_form_context(contract, notice),
        )

def _register_notice_action_routes(bp):
    def _action(notice_id, func, success):
        notice = ledger_store.get_production_notice(notice_id)
        if not notice:
            return '投产通知不存在', 404
        try:
            result = func(notice_id)
            suffix = ''
            if isinstance(result, dict):
                suffix = f"，生成 {len(result.get('payment_plan_ids', []))} 条动态付款计划"
            return redirect(url_for(
                'production_notice_detail', notice_id=notice_id,
                message=f'{success}{suffix}',
            ))
        except ValueError as exc:
            return redirect(url_for(
                'production_notice_detail', notice_id=notice_id, error=str(exc)
            ))

    @bp.route('/production-notices/<int:notice_id>/issue', methods=['POST'])
    def production_notice_issue(notice_id):
        operator = request.form.get('operator', '').strip()
        return _action(
            notice_id,
            lambda current: ledger_store.issue_production_notice(current, operator),
            '投产通知已正式发出并锁定',
        )

    @bp.route('/production-notices/<int:notice_id>/acknowledge', methods=['POST'])
    def production_notice_acknowledge(notice_id):
        operator = request.form.get('operator', '').strip()
        return _action(
            notice_id,
            lambda current: ledger_store.acknowledge_production_notice(current, operator),
            '已登记供应商收悉',
        )

    @bp.route('/production-notices/<int:notice_id>/close', methods=['POST'])
    def production_notice_close(notice_id):
        operator = request.form.get('operator', '').strip()
        return _action(
            notice_id,
            lambda current: ledger_store.close_production_notice(current, operator),
            '投产通知已关闭',
        )

    @bp.route('/production-notices/<int:notice_id>/cancel', methods=['POST'])
    def production_notice_cancel(notice_id):
        operator = request.form.get('operator', '').strip()
        reason = request.form.get('reason', '').strip()
        return _action(
            notice_id,
            lambda current: ledger_store.cancel_production_notice(current, operator, reason),
            '投产通知已取消',
        )

    @bp.route('/production-notices/<int:notice_id>/revise', methods=['POST'])
    def production_notice_revise(notice_id):
        operator = request.form.get('operator', '').strip()
        notice = ledger_store.get_production_notice(notice_id)
        if not notice:
            return '投产通知不存在', 404
        try:
            new_id = ledger_store.revise_production_notice(notice_id, operator)
            return redirect(url_for('production_notice_edit', notice_id=new_id))
        except ValueError as exc:
            return redirect(url_for(
                'production_notice_detail', notice_id=notice_id, error=str(exc)
            ))

def register(app):
    bp = LegacyEndpointBlueprint('production', __name__)
    _register_contract_item_routes(bp)
    _register_notice_routes(bp)
    _register_notice_action_routes(bp)
    app.register_blueprint(bp)
