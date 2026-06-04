"""Contract generation and ledger routes: index, generate, batch, detail, download, update."""

import os
import uuid
import json
import zipfile
from datetime import date

from flask import render_template, request, redirect, url_for, send_file, session

import template_def
import ledger_store
import pdf_exporter
import xlsx_exporter
from utils import helpers
from utils.generation_utils import generate_docx_document
from utils.security import MAX_BATCH_CONTRACTS, MAX_COUNTERPARTY_LENGTH, limit_text
from utils.logger import get_logger


def register(app):
    @app.route('/')
    def index():
        today = date.today()
        contract_stats = ledger_store.get_contract_stats()
        payment_stats = ledger_store.get_payment_stats()
        this_month = ledger_store.get_monthly_payments(today.year, today.month)
        next_ym = helpers.next_month_ym(today)
        next_month = ledger_store.get_monthly_payments(next_ym[0], next_ym[1])
        due_soon = ledger_store.get_due_soon_payments(days=7)
        expiring_contracts = ledger_store.get_expiring_contracts(days=30)
        recent_contracts = ledger_store.get_recent_contracts(5)
        recent_templates = template_def.list_templates()[:5]
        autostart = helpers.autostart_status()

        status_labels = helpers.CONTRACT_STATUS_LABELS

        return render_template('index.html',
            contract_stats=contract_stats,
            payment_stats=payment_stats,
            this_month=this_month,
            next_month=next_month,
            due_soon=due_soon,
            expiring_contracts=expiring_contracts,
            recent_contracts=recent_contracts,
            recent_templates=recent_templates,
            status_labels=status_labels,
            today=today,
            autostart=autostart,
            autostart_error=request.args.get('autostart_error', ''),
        )

    @app.route('/editor')
    def editor():
        sid = session.get('sid')
        if not sid:
            return redirect(url_for('index'))

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return redirect(url_for('index'))

        return render_template(
            'editor.html',
            fields=data.get('fields', []),
            field_count=len(data.get('fields', [])),
            template_name=data.get('template_name', '未命名'),
        )

    @app.route('/generate', methods=['POST'])
    def generate():
        sid = session.get('sid')
        if not sid:
            return redirect(url_for('index'))

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return redirect(url_for('index'))

        template_path_data = helpers.template_path_from_session(data)
        if not template_path_data or not os.path.exists(template_path_data):
            return '未找到模板数据，请返回重新选择模板', 400

        tpl = template_def.TemplateDef.load(template_path_data)
        fields = tpl.data['fields']
        source_docx = tpl.data.get('source_docx', '')

        input_errors = helpers.apply_submitted_table_columns(fields, request.form)
        field_values, parse_errors = helpers.parse_submitted_field_values(fields, request.form)
        input_errors.extend(parse_errors)

        if input_errors:
            return '\n'.join(input_errors), 400

        helpers.recalculate_table_fields(fields, field_values)
        calc_errors = helpers.recalculate_scalar_fields(fields, field_values)
        if calc_errors:
            return '\n'.join(calc_errors), 400

        raw_name = data.get('raw_name', data.get('template_name', '合同'))
        output_name = f'{os.path.splitext(raw_name)[0]}_已生成.docx'
        output_path = os.path.join(helpers.OUTPUT_FOLDER, f'{sid}_{uuid.uuid4().hex[:8]}_output.docx')

        template_path = ''
        if source_docx:
            try:
                template_path = helpers.safe_uploaded_docx_path(source_docx)
            except ValueError as e:
                return str(e), 400

        gen_errors, output_path = generate_docx_document(
            tpl.data, fields, field_values, template_path, output_path
        )
        if gen_errors:
            return '合同生成失败：\n' + '\n'.join(gen_errors), 500

        contract_id = None
        ledger_error = ''
        try:
            contract_id = helpers.create_ledger_record(tpl, fields, field_values, output_path)
        except Exception as e:
            get_logger().error('Ledger save failed: %s', e, exc_info=True)
            ledger_error = str(e)

        pdf_url = ''
        if request.form.get('generate_pdf') == '1':
            try:
                pdf_path = os.path.splitext(output_path)[0] + '.pdf'
                pdf_exporter.convert_docx_to_pdf(output_path, pdf_path)
                if contract_id:
                    pdf_url = url_for('contract_download_pdf', contract_id=contract_id)
            except Exception as e:
                get_logger().warning('PDF export failed: %s', e)

        response = send_file(
            output_path,
            as_attachment=True,
            download_name=output_name,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        if contract_id:
            response.headers['X-Contract-Id'] = str(contract_id)
            response.headers['X-Contract-Detail-Url'] = url_for('contract_detail', contract_id=contract_id)
        if ledger_error:
            response.headers['X-Ledger-Error'] = ledger_error[:500]
        if pdf_url:
            response.headers['X-PDF-Url'] = pdf_url
        return response

    @app.route('/generate-batch', methods=['POST'])
    def generate_batch():
        sid = session.get('sid')
        if not sid:
            return '会话已过期，请重新选择模板', 400

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return '会话已过期，请重新选择模板', 400

        tpl_path = helpers.template_path_from_session(data)
        if not tpl_path:
            return '找不到模板信息', 400

        try:
            tpl = template_def.TemplateDef.load(tpl_path)
        except Exception:
            return '加载模板失败', 500

        tpl_name = data.get('template_name', '') or tpl.name
        fields = tpl.data.get('fields', [])

        input_errors = helpers.apply_submitted_table_columns(fields, request.form)
        field_values, parse_errors = helpers.parse_submitted_field_values(fields, request.form)
        input_errors.extend(parse_errors)
        if input_errors:
            return '\n'.join(input_errors), 400

        helpers.recalculate_table_fields(fields, field_values)
        calc_errors = helpers.recalculate_scalar_fields(fields, field_values)
        if calc_errors:
            return '\n'.join(calc_errors), 400

        counterparties_text = request.form.get('batch_counterparties', '').strip()
        counterparties = [c.strip() for c in counterparties_text.split('\n') if c.strip()]
        if not counterparties:
            return '请至少输入一个对方单位', 400
        if len(counterparties) > MAX_BATCH_CONTRACTS:
            return f'批量生成每次不能超过 {MAX_BATCH_CONTRACTS} 份合同', 400
        if any(len(c) > MAX_COUNTERPARTY_LENGTH for c in counterparties):
            return f'对方单位名称不能超过 {MAX_COUNTERPARTY_LENGTH} 个字符', 400

        batch_field_keys = helpers.counterparty_batch_keys(fields, request.form.get('batch_field_key', '').strip())
        if not batch_field_keys:
            return '未能识别对方单位字段，请在"字段变量名"中手动指定', 400

        source_docx = tpl.data.get('source_docx', '')
        try:
            template_path = helpers.safe_uploaded_docx_path(source_docx) if source_docx else ''
        except ValueError as e:
            return str(e), 400

        zip_path = os.path.join(helpers.OUTPUT_FOLDER, f'{sid}_{uuid.uuid4().hex[:8]}_batch.zip')
        gen_errors = []
        batch_temp_files = []
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, counterparty in enumerate(counterparties):
                batch_values = dict(field_values)
                for batch_field_key in batch_field_keys:
                    batch_values[batch_field_key] = counterparty

                suffix = helpers.safe_filename_part(counterparty, f'contract_{idx + 1}')[:30]
                out_path = os.path.join(helpers.OUTPUT_FOLDER, f'{sid}_batch_{idx}_{suffix}.docx')

                doc_errors, out_path = generate_docx_document(
                    tpl.data, fields, batch_values, template_path, out_path
                )
                for doc_err in doc_errors:
                    gen_errors.append(f'{counterparty}: {doc_err}')

                try:
                    helpers.create_ledger_record(tpl, fields, batch_values, out_path)
                except Exception as e:
                    get_logger().error('Batch ledger save failed for %s: %s', counterparty, e, exc_info=True)
                    gen_errors.append(f'{counterparty}: 台账入账失败 - {e}')

                zf.write(out_path, f'{helpers.safe_filename_part(counterparty, f"contract_{idx + 1}")}_合同.docx')
                batch_temp_files.append(out_path)

        # 打包完成后即时清理中间 DOCX 文件
        for tmp_path in batch_temp_files:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        download_name = f'{tpl_name}_批量合同_{len(counterparties)}份.zip' if tpl_name else f'批量合同_{len(counterparties)}份.zip'
        response = send_file(
            zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/zip',
        )
        if gen_errors:
            response.headers['X-Generation-Errors'] = '; '.join(gen_errors[:5])
        return response

    @app.route('/contracts')
    def contract_ledger():
        q = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        result = ledger_store.list_contracts(q=q, status=status, page=page)
        return render_template(
            'contracts.html',
            contracts=result['rows'],
            q=q,
            status=status,
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
        )

    @app.route('/contracts/export')
    def contract_export():
        q = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        result = ledger_store.list_contracts(q=q, status=status, page=1, per_page=10000)
        contracts = result['rows']
        filename = f'contracts_{date.today().strftime("%Y%m%d")}_{uuid.uuid4().hex[:8]}.xlsx'
        output_path = os.path.join(helpers.OUTPUT_FOLDER, filename)
        xlsx_exporter.export_contracts(output_path, contracts, title='合同台账')
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'合同台账_{date.today().strftime("%Y%m%d")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @app.route('/contracts/batch-delete', methods=['POST'])
    def contract_batch_delete():
        ids_json = request.form.get('ids', '[]')
        try:
            ids = [int(i) for i in json.loads(ids_json)]
        except (json.JSONDecodeError, TypeError, ValueError):
            return '无效的 ID 列表', 400
        if len(ids) > MAX_BATCH_CONTRACTS:
            return f'单次不能超过 {MAX_BATCH_CONTRACTS} 条记录', 400
        count = ledger_store.batch_delete_contracts(ids)
        get_logger().info('Batch deleted %d contracts: %s', count, ids)
        return redirect(url_for('contract_ledger'))

    @app.route('/contracts/batch-status', methods=['POST'])
    def contract_batch_status():
        ids_json = request.form.get('ids', '[]')
        new_status = request.form.get('status', '').strip()
        if new_status not in ('draft', 'signed', 'active', 'completed', 'void'):
            return '无效的状态值', 400
        try:
            ids = [int(i) for i in json.loads(ids_json)]
        except (json.JSONDecodeError, TypeError, ValueError):
            return '无效的 ID 列表', 400
        if len(ids) > MAX_BATCH_CONTRACTS:
            return f'单次不能超过 {MAX_BATCH_CONTRACTS} 条记录', 400
        count = ledger_store.batch_update_status(ids, new_status)
        get_logger().info('Batch updated %d contracts to status %s', count, new_status)
        return redirect(url_for('contract_ledger'))

    @app.route('/contracts/trash')
    def contract_trash():
        """回收站 — 查看已软删除的合同（分页检索全量已删除合同）"""
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        per_page = 20
        # 拉取所有已删除合同（不做分页过滤，先获取全集再分页）
        all_result = ledger_store.list_contracts(page=1, per_page=10000, include_deleted=True)
        trashed_all = [r for r in all_result['rows'] if r.get('deleted_at')]
        total = len(trashed_all)
        pages = (total + per_page - 1) // per_page if total > 0 else 1
        offset = (page - 1) * per_page
        trashed_page = trashed_all[offset:offset + per_page]
        return render_template(
            'contracts.html',
            contracts=trashed_page,
            q='',
            status='',
            page=page,
            pages=pages,
            total=total,
            trash_mode=True,
        )

    @app.route('/contracts/<int:contract_id>/soft-delete', methods=['POST'])
    def contract_soft_delete(contract_id):
        """软删除合同（移入回收站）"""
        count = ledger_store.soft_delete_contract(contract_id)
        if count == 0:
            return '合同不存在或已在回收站中', 404
        get_logger().info('Soft deleted contract %d', contract_id)
        return redirect(url_for('contract_ledger'))

    @app.route('/contracts/<int:contract_id>/restore', methods=['POST'])
    def contract_restore(contract_id):
        """从回收站恢复合同"""
        count = ledger_store.restore_contract(contract_id)
        if count == 0:
            return '合同不在回收站中', 404
        get_logger().info('Restored contract %d from trash', contract_id)
        return redirect(url_for('contract_trash'))

    @app.route('/contracts/<int:contract_id>/permanent-delete', methods=['POST'])
    def contract_permanent_delete(contract_id):
        """永久删除合同（仅在回收站中可操作）"""
        count = ledger_store.permanently_delete_contract(contract_id)
        if count == 0:
            return '合同不在回收站中或无法删除', 404
        get_logger().info('Permanently deleted contract %d', contract_id)
        return redirect(url_for('contract_trash'))

    @app.route('/contracts/<int:contract_id>')
    def contract_detail(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        plans = ledger_store.list_payment_plans(contract_id=contract_id)
        history = ledger_store.get_contract_history(contract_id)
        return render_template(
            'contract_detail.html',
            contract=contract,
            plans=plans,
            history=history,
        )

    @app.route('/contracts/<int:contract_id>/download')
    def contract_download(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        docx_path = contract.get('docx_path') or ''
        if not docx_path or not helpers.path_within(helpers.OUTPUT_FOLDER, docx_path) or not os.path.exists(docx_path):
            return '合同文件不存在，可能已被移动或删除', 404
        base = contract.get('contract_no') or f'contract_{contract_id}'
        return send_file(
            docx_path,
            as_attachment=True,
            download_name=f'{base}.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    @app.route('/contracts/<int:contract_id>/download-pdf')
    def contract_download_pdf(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        docx_path = contract.get('docx_path') or ''
        if not docx_path or not helpers.path_within(helpers.OUTPUT_FOLDER, docx_path) or not os.path.exists(docx_path):
            return '合同文件不存在，可能已被移动或删除', 404
        base = contract.get('contract_no') or f'contract_{contract_id}'
        safe_base = helpers.safe_filename_part(base, f'contract_{contract_id}')
        pdf_path = os.path.abspath(os.path.join(helpers.OUTPUT_FOLDER, f'{safe_base}.pdf'))
        if not helpers.path_within(helpers.OUTPUT_FOLDER, pdf_path):
            return 'PDF 输出路径无效', 400
        try:
            pdf_exporter.convert_docx_to_pdf(docx_path, pdf_path)
        except Exception as e:
            return f'PDF 导出失败：{e}', 500
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'{safe_base}.pdf',
            mimetype='application/pdf',
        )

    @app.route('/contracts/<int:contract_id>/update', methods=['POST'])
    def contract_update(contract_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        new_status = request.form.get('status', 'draft').strip() or 'draft'
        if new_status not in {'draft', 'signed', 'active', 'completed', 'void'}:
            return '无效的状态值', 400
        try:
            ledger_store.update_contract(contract_id, {
                'contract_no': request.form.get('contract_no', '').strip(),
                'title': request.form.get('title', '').strip() or '未命名合同',
                'counterparty': request.form.get('counterparty', '').strip(),
                'amount': helpers.float_or_none(request.form.get('amount')),
                'sign_date': helpers.normalize_date(request.form.get('sign_date')) or '',
                'expiry_date': helpers.normalize_date(request.form.get('expiry_date')) or '',
                'owner': request.form.get('owner', '').strip(),
                'status': new_status,
            })
        except ValueError as e:
            return str(e), 400
        return redirect(url_for('contract_detail', contract_id=contract_id))
