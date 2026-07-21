"""External DOCX contract import routes."""

from __future__ import annotations

import os
import time
import uuid

from flask import current_app, redirect, render_template, request, session, url_for

import ledger_store
from config import config as app_config
from routes.legacy_blueprint import LegacyEndpointBlueprint
from services.contract_import_service import ContractImportRequest
from utils import helpers
from utils.generation_utils import has_payment_content
from utils.logger import get_logger
from utils.payment_forms import payment_row_from_form
from utils.security import (
    MAX_COUNTERPARTY_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
    limit_text,
    safe_join_file,
)


MAX_IMPORTED_PLANS = 30


def _session_file_path(sid):
    return safe_join_file(helpers.SESSION_FOLDER, f'{sid}.json', allowed_ext={'.json'})


def _discard_import_session(sid):
    """Remove one unconfirmed import session and its staged upload."""
    if not sid:
        return
    try:
        data = helpers.load_session_data(sid)
        if data.get('kind') == 'contract_import' and not data.get('confirmed_contract_id'):
            staging = _staging_path(data)
            if os.path.isfile(staging):
                os.remove(staging)
    except (FileNotFoundError, OSError, ValueError):
        get_logger().info('合同导入暂存会话已不存在: %s', sid)
    _delete_session_file(sid)


def _session_data(sid):
    if not sid or session.get('contract_import_sid') != sid:
        raise ValueError('合同导入会话不存在或已过期')
    path = _session_file_path(sid)
    ttl_seconds = max(1, int(app_config.SESSION_TTL_HOURS)) * 3600
    if not os.path.isfile(path) or os.path.getmtime(path) < time.time() - ttl_seconds:
        _discard_import_session(sid)
        session.pop('contract_import_sid', None)
        raise ValueError('合同导入会话不存在或已过期')
    data = helpers.load_session_data(sid)
    if data.get('kind') != 'contract_import':
        raise ValueError('合同导入会话无效')
    return data


def _staging_path(data):
    return safe_join_file(
        helpers.UPLOAD_FOLDER,
        data.get('staging_name', ''),
        allowed_ext={'.docx'},
    )


def _delete_session_file(sid):
    try:
        path = _session_file_path(sid)
        if os.path.isfile(path):
            os.remove(path)
    except (OSError, ValueError):
        get_logger().warning('无法清理合同导入会话 %s', sid, exc_info=True)


def _normalized_date(form, name, label):
    raw = str(form.get(name, '') or '').strip()
    if not raw:
        return ''
    value = helpers.normalize_date(raw)
    if not value:
        raise ValueError(f'{label}格式无效，请使用 YYYY-MM-DD')
    return value


def _summary_from_form(form):
    title = limit_text(str(form.get('title', '') or '').strip(), 200)
    if not title:
        raise ValueError('合同名称不能为空')
    amount_raw = str(form.get('amount', '') or '').strip()
    amount = helpers.float_or_none(amount_raw)
    if amount_raw and amount is None:
        raise ValueError('合同金额必须是有效数字')
    if amount is not None and amount < 0:
        raise ValueError('合同金额不能为负数')
    status = str(form.get('status', 'draft') or 'draft').strip()
    if status not in ledger_store.CONTRACT_STATUSES:
        raise ValueError('合同状态无效')
    classification = helpers.parse_contract_classification(form)
    return {
        'contract_no': limit_text(str(form.get('contract_no', '') or '').strip(), 80),
        'title': title,
        'counterparty': limit_text(
            str(form.get('counterparty', '') or '').strip(),
            MAX_COUNTERPARTY_LENGTH,
        ),
        'amount': amount,
        'sign_date': _normalized_date(form, 'sign_date', '签订日期'),
        'expiry_date': _normalized_date(form, 'expiry_date', '到期日期'),
        'owner': limit_text(str(form.get('owner', '') or '').strip(), 60),
        'status': status,
        'project_name': limit_text(
            classification.get('project_name') or '', MAX_PROJECT_NAME_LENGTH
        ),
        'coverage_start': classification.get('coverage_start'),
        'coverage_end': classification.get('coverage_end'),
    }


def _summary_for_render(form):
    """Keep user-entered values visible when strict validation rejects the form."""
    keys = (
        'contract_no', 'title', 'counterparty', 'amount', 'sign_date',
        'expiry_date', 'owner', 'status', 'project_name', 'coverage_start',
        'coverage_end',
    )
    return {key: str(form.get(key, '') or '').strip() for key in keys}


def _plans_for_render(form):
    """Capture editable payment rows without applying persistence validation."""
    try:
        count = min(max(int(form.get('plan_count', 0)), 0), MAX_IMPORTED_PLANS)
    except (TypeError, ValueError):
        return []
    keys = (
        'phase_name', 'payment_type', 'trigger_event', 'trigger_days',
        'expected_trigger_date', 'due_date', 'ratio', 'due_amount',
        'condition_text', 'source_text', 'confidence', 'remark',
    )
    rows = []
    for index in range(count):
        prefix = f'plan_{index}_'
        row = {
            key: str(form.get(prefix + key, '') or '').strip()
            for key in keys
        }
        row['_include'] = str(form.get(prefix + 'include', '') or '') == '1'
        rows.append(row)
    return rows


def _plans_from_form(form):
    try:
        count = int(form.get('plan_count', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('付款计划行数无效') from exc
    if count < 0 or count > MAX_IMPORTED_PLANS:
        raise ValueError(f'导入时付款计划不能超过 {MAX_IMPORTED_PLANS} 条')
    plans = []
    for index in range(count):
        if str(form.get(f'plan_{index}_include', '') or '') != '1':
            continue
        row = payment_row_from_form(index, form)
        row.pop('id', None)
        row['confirm_status'] = 'pending'
        row['payment_status'] = 'unpaid'
        row['paid_amount'] = 0
        row['paid_date'] = ''
        if has_payment_content(row):
            plans.append(row)
    return plans


def _render_review(sid, data, *, error='', submitted_summary=None, submitted_plans=None,
                   duplicate_contract=None, status=200):
    preview = data['preview']
    diagnostics = {
        item.get('field'): item for item in preview.get('diagnostics', [])
        if item.get('field')
    }
    return render_template(
        'contract_import_review.html',
        sid=sid,
        preview=preview,
        summary=submitted_summary or preview.get('summary', {}),
        plans=submitted_plans if submitted_plans is not None else preview.get('plans', []),
        diagnostics=diagnostics,
        project_names=ledger_store.list_project_names(),
        duplicate_contract=duplicate_contract,
        error=error,
    ), status


def _register_upload_routes(bp):
    @bp.route('/contracts/import')
    def contract_import():
        return render_template('contract_import.html', error=request.args.get('error', ''))

    @bp.route('/contracts/import/preview', methods=['POST'])
    def contract_import_preview():
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return render_template('contract_import.html', error='请选择 DOCX 合同文件'), 400
        original_name = os.path.basename(upload.filename)[:255]
        if os.path.splitext(original_name)[1].lower() != '.docx':
            return render_template('contract_import.html', error='仅支持 .docx 格式'), 400

        previous_sid = session.get('contract_import_sid')
        if previous_sid:
            _discard_import_session(previous_sid)
            session.pop('contract_import_sid', None)

        sid = uuid.uuid4().hex
        staging_name = f'contract_import_{sid}.docx'
        staging_path = safe_join_file(
            helpers.UPLOAD_FOLDER, staging_name, allowed_ext={'.docx'}
        )
        try:
            upload.save(staging_path)
            preview = current_app.extensions['contract_tool'].contract_import.preview_file(
                staging_path, original_name
            )
            helpers.save_session_data(sid, {
                'kind': 'contract_import',
                'staging_name': staging_name,
                'preview': preview.to_dict(),
                'confirmed_contract_id': None,
            })
            session['contract_import_sid'] = sid
            return redirect(url_for('contract_import_review', sid=sid))
        except ValueError as exc:
            try:
                if os.path.isfile(staging_path):
                    os.remove(staging_path)
            except OSError:
                get_logger().warning('合同导入预览失败后无法清理文件', exc_info=True)
            duplicate = None
            contract_id = getattr(exc, 'contract_id', None)
            if contract_id:
                duplicate = ledger_store.get_contract(contract_id)
            return render_template(
                'contract_import.html', error=str(exc), duplicate_contract=duplicate
            ), 409 if duplicate else 400
        except Exception:
            try:
                if os.path.isfile(staging_path):
                    os.remove(staging_path)
            except OSError:
                get_logger().warning('合同导入解析异常后无法清理文件', exc_info=True)
            get_logger().error('合同导入预览失败', exc_info=True)
            return render_template(
                'contract_import.html', error='合同解析失败，请确认文件有效后重试'
            ), 400

def _register_confirmation_routes(bp):
    @bp.route('/contracts/import/<sid>/review')
    def contract_import_review(sid):
        try:
            data = _session_data(sid)
            if data.get('confirmed_contract_id'):
                return redirect(url_for(
                    'contract_detail', contract_id=data['confirmed_contract_id']
                ))
            if not os.path.isfile(_staging_path(data)):
                raise ValueError('暂存合同已过期，请重新上传')
        except (FileNotFoundError, ValueError):
            return redirect(url_for('contract_import', error='合同导入会话已过期，请重新上传'))
        return _render_review(sid, data)

    @bp.route('/contracts/import/<sid>/confirm', methods=['POST'])
    def contract_import_confirm(sid):
        try:
            data = _session_data(sid)
        except (FileNotFoundError, ValueError):
            return redirect(url_for('contract_import', error='合同导入会话已过期，请重新上传'))
        if data.get('confirmed_contract_id'):
            return redirect(url_for(
                'contract_detail', contract_id=data['confirmed_contract_id']
            ))

        preview = data['preview']
        staging_path = _staging_path(data)
        if not os.path.isfile(staging_path):
            existing = ledger_store.get_contract_by_source_sha256(
                preview.get('source_sha256')
            )
            if existing:
                data['confirmed_contract_id'] = existing['id']
                helpers.save_session_data(sid, data)
                return redirect(url_for('contract_detail', contract_id=existing['id']))
            return redirect(url_for(
                'contract_import', error='暂存合同已过期，请重新上传'
            ))

        summary = None
        plans = None
        submitted_summary = _summary_for_render(request.form)
        submitted_plans = _plans_for_render(request.form)
        try:
            summary = _summary_from_form(request.form)
            plans = _plans_from_form(request.form)
            if summary['contract_no']:
                existing_id = ledger_store.contract_no_exists(summary['contract_no'])
                if existing_id:
                    raise ValueError('合同编号已存在，请修改后再导入')
            result = current_app.extensions['contract_tool'].contract_import.finalize(
                ContractImportRequest(
                    staging_path=_staging_path(data),
                    original_filename=preview['original_filename'],
                    source_sha256=preview['source_sha256'],
                    summary=summary,
                    plans=plans,
                )
            )
            data['confirmed_contract_id'] = result.contract_id
            helpers.save_session_data(sid, data)
            get_logger().info(
                'Imported contract %d from %s with %d payment plan(s)',
                result.contract_id,
                preview['original_filename'],
                result.plan_count,
            )
            return redirect(url_for('contract_detail', contract_id=result.contract_id))
        except ValueError as exc:
            duplicate = None
            contract_id = getattr(exc, 'contract_id', None)
            if contract_id:
                duplicate = ledger_store.get_contract(contract_id)
            if duplicate is None:
                duplicate = ledger_store.get_contract_by_source_sha256(
                    preview.get('source_sha256')
                )
            if duplicate and not os.path.isfile(staging_path):
                data['confirmed_contract_id'] = duplicate['id']
                helpers.save_session_data(sid, data)
                return redirect(url_for(
                    'contract_detail', contract_id=duplicate['id']
                ))
            elif summary and summary.get('contract_no'):
                with ledger_store.get_conn() as conn:
                    row = conn.execute(
                        'SELECT id FROM contracts WHERE contract_no = ? LIMIT 1',
                        (summary['contract_no'],),
                    ).fetchone()
                duplicate = ledger_store.get_contract(row['id']) if row else None
            return _render_review(
                sid, data, error=str(exc),
                submitted_summary=summary or submitted_summary,
                submitted_plans=submitted_plans,
                duplicate_contract=duplicate, status=409,
            )
        except Exception:
            get_logger().error('确认导入合同时发生异常', exc_info=True)
            return _render_review(
                sid, data, error='合同导入失败，数据未写入，请重试',
                submitted_summary=summary or submitted_summary,
                submitted_plans=submitted_plans, status=500,
            )

    @bp.route('/contracts/import/<sid>/cancel', methods=['POST'])
    def contract_import_cancel(sid):
        try:
            _session_data(sid)
            _discard_import_session(sid)
        except (FileNotFoundError, OSError, ValueError):
            get_logger().info('取消合同时暂存会话已不存在: %s', sid)
        if session.get('contract_import_sid') == sid:
            session.pop('contract_import_sid', None)
        return redirect(url_for('contract_ledger'))

def register(app):
    bp = LegacyEndpointBlueprint('contract_import', __name__)
    _register_upload_routes(bp)
    _register_confirmation_routes(bp)
    app.register_blueprint(bp)
