"""Incoming invoice maintenance, allocation, and attachment routes."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import safe_join, secure_filename

import ledger_store
from core.domain_errors import ConflictError
from utils.field_utils import float_or_none, normalize_date
from utils.logger import get_logger


MAX_ALLOCATION_ROWS = 100
ALLOWED_INVOICE_FILE_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.ofd', '.xml'}


def _form_date(form, key, label):
    raw = str(form.get(key, '') or '').strip()
    if not raw:
        return ''
    normalized = normalize_date(raw)
    if not normalized:
        raise ValueError(f'{label}格式无效，请使用 YYYY-MM-DD')
    return normalized


def _invoice_data(form):
    for key, label in (
        ('amount_ex_tax', '不含税金额'),
        ('tax_amount', '税额'),
        ('total_amount', '价税合计'),
    ):
        if float_or_none(form.get(key)) is None:
            raise ValueError(f'{label}必须是有效金额')
    tax_rate_raw = str(form.get('tax_rate', '') or '').strip()
    if tax_rate_raw and float_or_none(tax_rate_raw) is None:
        raise ValueError('税率必须是有效数字')
    currency = str(form.get('currency', 'CNY') or 'CNY').strip().upper()
    if currency != 'CNY':
        raise ValueError('发票币种仅支持 CNY（人民币）')
    return {
        'invoice_code': form.get('invoice_code', ''),
        'invoice_no': form.get('invoice_no', ''),
        'invoice_type': form.get('invoice_type', 'vat_special'),
        'issue_date': _form_date(form, 'issue_date', '开票日期'),
        'received_date': _form_date(form, 'received_date', '收票日期'),
        'seller_name': form.get('seller_name', ''),
        'seller_tax_no': form.get('seller_tax_no', ''),
        'buyer_name': form.get('buyer_name', ''),
        'buyer_tax_no': form.get('buyer_tax_no', ''),
        'currency': 'CNY',
        'amount_ex_tax': form.get('amount_ex_tax', ''),
        'tax_amount': form.get('tax_amount', ''),
        'total_amount': form.get('total_amount', ''),
        'tax_rate': tax_rate_raw,
        'invoice_status': form.get('invoice_status', 'valid'),
        'review_status': form.get('review_status', 'pending'),
        'deduction_status': form.get('deduction_status', 'not_applicable'),
        'original_invoice_id': form.get('original_invoice_id', ''),
        'remark': form.get('remark', ''),
        'operator': form.get('operator', ''),
    }


def _allocation_rows(form):
    try:
        count = int(form.get('allocation_count', 0))
    except (TypeError, ValueError) as exc:
        raise ValueError('发票分摊行数无效') from exc
    if count < 0 or count > MAX_ALLOCATION_ROWS:
        raise ValueError(f'发票分摊行数必须在 0 到 {MAX_ALLOCATION_ROWS} 之间')
    rows = []
    for index in range(count):
        rows.append({
            'contract_id': form.get(f'allocation_{index}_contract_id', ''),
            'production_notice_id': form.get(
                f'allocation_{index}_production_notice_id', ''
            ),
            'payment_plan_id': form.get(f'allocation_{index}_payment_plan_id', ''),
            'allocated_amount': form.get(f'allocation_{index}_allocated_amount', ''),
            'remark': form.get(f'allocation_{index}_remark', ''),
        })
    return rows


def _invoice_revision(form):
    raw = str(form.get('revision', '') or '').strip()
    if not raw:
        raise ValueError('缺少发票版本，请刷新页面后重新提交')
    try:
        revision = int(raw)
    except ValueError as exc:
        raise ValueError('发票版本无效，请刷新页面后重新提交') from exc
    if revision <= 0:
        raise ValueError('发票版本无效，请刷新页面后重新提交')
    return revision


def _invoice_form_context(invoice=None, *, error='', selected_contract_id=None):
    contracts = list(ledger_store.iter_contracts(batch_size=500))
    contract_ids = {int(selected_contract_id)} if selected_contract_id else set()
    if invoice:
        for allocation in invoice.get('allocations', []) or []:
            try:
                contract_id = int(allocation.get('contract_id') or 0)
            except (TypeError, ValueError):
                contract_id = 0
            if contract_id:
                contract_ids.add(contract_id)
    notices = []
    plans = []
    for contract_id in sorted(contract_ids):
        notices.extend(
            item for item in ledger_store.list_production_notices(contract_id)
            if item['status'] in {'issued', 'acknowledged', 'closed'}
        )
        plans.extend(
            item for item in ledger_store.list_payment_plans(contract_id=contract_id)
            if item['confirm_status'] != 'void'
        )
    return {
        'invoice': invoice,
        'contracts': contracts,
        'notices': notices,
        'plans': plans,
        'selected_contract_id': selected_contract_id,
        'today': date.today().strftime('%Y-%m-%d'),
        'error': error,
    }


def _invoice_storage_root():
    root = (Path(current_app.extensions['runtime_paths'].data_dir) / 'invoice_files').resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolved_invoice_file(storage_path):
    root = _invoice_storage_root()
    joined = safe_join(str(root), str(storage_path or ''))
    if joined is None:
        raise ValueError('发票附件路径无效')
    candidate = Path(joined).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError('发票附件路径无效')
    return candidate


def _register_invoice_routes(bp):
    @bp.route('/invoices')
    def invoice_list():
        review_status = request.args.get('review_status', '').strip()
        invoice_status = request.args.get('invoice_status', '').strip()
        page = max(1, request.args.get('page', 1, type=int) or 1)
        if review_status not in {'', 'pending', 'verified', 'exception'}:
            review_status = ''
        if invoice_status not in {'', 'valid', 'red', 'void'}:
            invoice_status = ''
        result = ledger_store.list_invoices(
            review_status=review_status, invoice_status=invoice_status, page=page
        )
        summary = ledger_store.summarize_invoices(
            review_status=review_status, invoice_status=invoice_status
        )
        return render_template(
            'invoice_list.html',
            invoices=result['rows'],
            review_status=review_status,
            invoice_status=invoice_status,
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
            summary=summary,
        )

    @bp.route('/api/contracts/<int:contract_id>/invoice-targets')
    def invoice_targets_api(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract or contract.get('deleted_at'):
            return jsonify({'error': '合同不存在'}), 404
        if contract.get('status') == 'void':
            return jsonify({'error': '已作废合同不能新增或修改发票分摊'}), 409
        notices = [
            item for item in ledger_store.list_production_notices(contract_id)
            if item['status'] in {'issued', 'acknowledged', 'closed'}
        ]
        plans = [
            item for item in ledger_store.list_payment_plans(contract_id=contract_id)
            if item['confirm_status'] != 'void'
        ]
        return jsonify({
            'notices': [{
                'id': item['id'],
                'label': f"{item['notice_no']} V{item['version']}",
            } for item in notices],
            'plans': [{
                'id': item['id'],
                'label': item.get('phase_name') or f"计划 #{item['id']}",
            } for item in plans],
        })

    @bp.route('/invoices/new', methods=['GET', 'POST'])
    def invoice_new():
        contract_id = request.args.get('contract_id', type=int)
        if request.method == 'POST':
            allocations = []
            try:
                allocations = _allocation_rows(request.form)
                invoice_id = ledger_store.save_invoice(
                    _invoice_data(request.form), allocations
                )
                return redirect(url_for('invoices.invoice_detail', invoice_id=invoice_id))
            except ValueError as exc:
                submitted = dict(request.form)
                submitted['allocations'] = allocations
                return render_template(
                    'invoice_form.html',
                    **_invoice_form_context(
                        submitted, error=str(exc), selected_contract_id=contract_id
                    ),
                ), 400
        return render_template(
            'invoice_form.html',
            **_invoice_form_context(selected_contract_id=contract_id),
        )

    @bp.route('/invoices/<int:invoice_id>')
    def invoice_detail(invoice_id):
        invoice = ledger_store.get_invoice(invoice_id)
        if not invoice:
            return '发票不存在', 404
        return render_template(
            'invoice_detail.html',
            invoice=invoice,
            error=request.args.get('error', ''),
            message=request.args.get('message', ''),
        )

    @bp.route('/invoices/<int:invoice_id>/edit', methods=['GET', 'POST'])
    def invoice_edit(invoice_id):
        invoice = ledger_store.get_invoice(invoice_id)
        if not invoice:
            return '发票不存在', 404
        if request.method == 'POST':
            allocations = []
            try:
                allocations = _allocation_rows(request.form)
                ledger_store.save_invoice(
                    _invoice_data(request.form), allocations,
                    invoice_id=invoice_id,
                    expected_revision=_invoice_revision(request.form),
                )
                return redirect(url_for('invoices.invoice_detail', invoice_id=invoice_id))
            except ConflictError as exc:
                submitted = dict(request.form)
                submitted['id'] = invoice_id
                submitted['allocations'] = allocations
                submitted['files'] = invoice.get('files', [])
                return render_template(
                    'invoice_form.html',
                    **_invoice_form_context(
                        submitted, error=exc.public_message
                    ),
                ), exc.status_code
            except ValueError as exc:
                submitted = dict(request.form)
                submitted['id'] = invoice_id
                submitted['allocations'] = allocations
                submitted['files'] = invoice.get('files', [])
                return render_template(
                    'invoice_form.html',
                    **_invoice_form_context(submitted, error=str(exc)),
                ), 400
        return render_template(
            'invoice_form.html', **_invoice_form_context(invoice)
        )

def _register_invoice_file_routes(bp):
    @bp.route('/invoices/<int:invoice_id>/files', methods=['POST'])
    def invoice_file_upload(invoice_id):
        if not ledger_store.get_invoice(invoice_id):
            return '发票不存在', 404
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return redirect(url_for(
                'invoices.invoice_detail', invoice_id=invoice_id, error='请选择发票附件'
            ))
        original_name = os.path.basename(upload.filename)[:255]
        extension = Path(original_name).suffix.lower()
        if extension not in ALLOWED_INVOICE_FILE_EXTENSIONS:
            return redirect(url_for(
                'invoices.invoice_detail', invoice_id=invoice_id,
                error='仅支持 PDF、JPG、PNG、OFD 或 XML 发票附件',
            ))
        safe_stem = secure_filename(Path(original_name).stem)[:60] or 'invoice'
        relative = Path(str(invoice_id)) / f'{safe_stem}_{uuid.uuid4().hex[:12]}{extension}'
        target = _resolved_invoice_file(relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        try:
            upload.save(target)
            with target.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            ledger_store.add_invoice_file(
                invoice_id,
                original_filename=original_name,
                storage_path=relative.as_posix(),
                content_type=upload.mimetype or '',
                file_size=target.stat().st_size,
                sha256=digest.hexdigest(),
            )
        except Exception as exc:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                get_logger().warning(
                    '发票附件登记失败后无法清理暂存文件: %s',
                    target,
                    exc_info=True,
                )
            if isinstance(exc, ValueError):
                return redirect(url_for(
                    'invoices.invoice_detail', invoice_id=invoice_id, error=str(exc)
                ))
            raise
        return redirect(url_for(
            'invoices.invoice_detail', invoice_id=invoice_id, message='发票附件已上传'
        ))

    @bp.route('/invoices/<int:invoice_id>/files/<int:file_id>/download')
    def invoice_file_download(invoice_id, file_id):
        stored = ledger_store.get_invoice_file(file_id, invoice_id=invoice_id)
        if not stored:
            return '发票附件不存在', 404
        try:
            path = _resolved_invoice_file(stored['storage_path'])
        except ValueError:
            return '发票附件路径无效', 400
        if not path.is_file():
            return '发票附件文件不存在', 404
        return send_file(
            path,
            as_attachment=True,
            download_name=stored['original_filename'],
            mimetype=stored['content_type'] or None,
        )

    @bp.route('/invoices/<int:invoice_id>/files/<int:file_id>/delete', methods=['POST'])
    def invoice_file_delete(invoice_id, file_id):
        stored = ledger_store.get_invoice_file(file_id, invoice_id=invoice_id)
        if not stored:
            return '发票附件不存在', 404
        source = None
        staged = None
        try:
            source = _resolved_invoice_file(stored['storage_path'])
            if source.exists():
                staged = _resolved_invoice_file(
                    f'.trash/{uuid.uuid4().hex}_{source.name}'
                )
                staged.parent.mkdir(parents=True, exist_ok=True)
                source.replace(staged)
            deleted = ledger_store.delete_invoice_file(file_id, invoice_id)
            if not deleted:
                if staged and staged.exists():
                    staged.replace(source)
                return '发票附件不存在', 404
        except Exception:
            if staged and staged.exists() and source is not None:
                source.parent.mkdir(parents=True, exist_ok=True)
                staged.replace(source)
            raise
        if staged:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                # The database no longer references this staged file.  Keeping it
                # in .trash is safer than reporting success after losing metadata.
                get_logger().warning(
                    '发票附件已移除数据库记录，但暂存文件清理失败: %s', staged,
                    exc_info=True,
                )
        return redirect(url_for(
            'invoices.invoice_detail', invoice_id=invoice_id, message='发票附件已删除'
        ))

def register(app):
    bp = Blueprint('invoices', __name__)
    _register_invoice_routes(bp)
    _register_invoice_file_routes(bp)
    app.register_blueprint(bp)
