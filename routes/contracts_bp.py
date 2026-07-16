"""Contract generation and ledger routes: index, generate, batch, detail, download, update."""

import os
import uuid
import json
import zipfile
from copy import deepcopy
from datetime import date
from urllib.parse import quote

from flask import current_app, render_template, request, redirect, url_for, send_file, session, jsonify

from routes.legacy_blueprint import LegacyEndpointBlueprint

from core.domain_errors import DocumentGenerationError, ProcurementLinkError, ValidationError
import template_def
import ledger_store
import pdf_exporter
import xlsx_exporter
from services import generation_preflight_service
from services import dashboard_service
from services.contract_preview_service import editor_preview_model
from services.contract_generation_service import ContractGenerationRequest, ProcurementLink
from utils import helpers
from utils.security import MAX_BATCH_CONTRACTS, MAX_COUNTERPARTY_LENGTH, limit_text
from utils.logger import get_logger
from utils.errors import safe_error, safe_file_error, GENERIC_ERROR, GENERIC_GENERATE_ERROR


def _remove_generated_file(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        get_logger().warning('Failed to remove generated file: %s', path, exc_info=True)


def _discard_generated_contract(contract_id, output_path):
    if contract_id:
        try:
            ledger_store.discard_unlinked_contract(contract_id)
        except Exception:
            get_logger().error(
                'Failed to discard unlinked generated contract %s', contract_id, exc_info=True
            )
    _remove_generated_file(output_path)


def register(app):
    bp = LegacyEndpointBlueprint('contracts', __name__)
    @bp.route('/')
    def index():
        today = date.today()
        snapshot = dashboard_service.build_dashboard_snapshot(today=today)
        # Windows scheduled-task discovery launches PowerShell and can take
        # several seconds. The page loads immediately and refreshes this
        # status through the asynchronous API instead.
        autostart = {'enabled': False, 'supported': os.name == 'nt'}
        return render_template('index.html',
            **snapshot,
            autostart=autostart,
            autostart_error=request.args.get('autostart_error', ''),
        )

    @bp.route('/editor')
    def editor():
        sid = session.get('sid')
        if not sid:
            return redirect(url_for('index'))

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return redirect(url_for('index'))

        # 确保所有字段都有 id（兼容旧版模板）
        fields = data.get('fields', [])
        for i, f in enumerate(fields):
            if 'id' not in f:
                f['id'] = i
        source_docx = data.get('stored_name') or data.get('source_docx', '')
        if not source_docx:
            template_path = helpers.template_path_from_session(data)
            if template_path:
                try:
                    source_docx = template_def.TemplateDef.load(template_path).data.get('source_docx', '')
                except Exception:
                    source_docx = ''

        preview_model = editor_preview_model(source_docx, fields)
        return render_template(
            'editor.html',
            fields=fields,
            field_count=len(fields),
            template_name=data.get('template_name', '未命名'),
            template_filename=data.get('template_filename', ''),
            preview_blocks=preview_model.get('blocks', []),
            preview_warnings=preview_model.get('warnings', []),
            project_names=ledger_store.list_project_names(),
            classification_project_name=data.get('project_name', ''),
            batch_allowed=not bool(data.get('procurement_data_sheet_id')),
        )

    @bp.route('/generate', methods=['POST'])
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

        field_values, input_errors = helpers.prepare_generation_values(fields, request.form)
        if input_errors:
            return '\n'.join(input_errors), 400

        try:
            classification = helpers.parse_contract_classification(request.form)
        except ValueError as e:
            return safe_error(e, '合同分类解析')

        raw_name = data.get('raw_name', data.get('template_name', '合同'))
        output_name = f'{os.path.splitext(raw_name)[0]}_已生成.docx'
        output_path = os.path.join(helpers.OUTPUT_FOLDER, f'{sid}_{uuid.uuid4().hex[:8]}_output.docx')

        template_path = ''
        if source_docx:
            try:
                template_path = helpers.safe_uploaded_docx_path(source_docx)
            except ValueError as e:
                return safe_file_error(e, '获取DOCX路径失败')

        source_id = data.get('source_id')
        link = None
        if data.get('procurement_data_sheet_id') or data.get('source_project_id'):
            link = ProcurementLink(
                data_sheet_id=(
                    int(data['procurement_data_sheet_id'])
                    if data.get('procurement_data_sheet_id') else None
                ),
                project_id=(
                    int(data['source_project_id'])
                    if data.get('source_project_id') else None
                ),
                source_type=data.get('source_type') or 'direct_contract',
                source_id=int(source_id) if source_id else None,
            )
        try:
            result = current_app.extensions['contract_tool'].contract_generation.generate(
                ContractGenerationRequest(
                    template=tpl,
                    fields=fields,
                    field_values=field_values,
                    source_docx=template_path,
                    output_path=output_path,
                    classification=classification,
                    link=link,
                )
            )
            contract_id = result.contract_id
            output_path = result.output_path
        except DocumentGenerationError as e:
            get_logger().error('合同生成失败: %s', e.detail)
            return GENERIC_GENERATE_ERROR, 500
        except ValidationError as e:
            return safe_error(e, '台账保存失败')
        except ProcurementLinkError as e:
            return safe_error(e, '采购项目关联失败', 500)
        except Exception as e:
            return safe_error(e, '合同生成事务失败', 500)

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
        if pdf_url:
            response.headers['X-PDF-Url'] = pdf_url
        return response

    @bp.route('/generate/preflight', methods=['POST'])
    def generate_preflight():
        sid = session.get('sid')
        if not sid:
            return jsonify({'ok': False, 'blocking': ['会话已过期，请重新选择模板'], 'warnings': []}), 400

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({'ok': False, 'blocking': ['会话已过期，请重新选择模板'], 'warnings': []}), 400

        tpl_path = helpers.template_path_from_session(data)
        if not tpl_path:
            return jsonify({'ok': False, 'blocking': ['找不到模板信息'], 'warnings': []}), 400

        try:
            tpl = template_def.TemplateDef.load(tpl_path)
        except Exception:
            return jsonify({'ok': False, 'blocking': ['加载模板失败'], 'warnings': []}), 500

        fields = tpl.data.get('fields', [])
        mode = request.form.get('_generation_mode', 'single')
        generate_pdf = request.form.get('generate_pdf') == '1'

        try:
            classification = helpers.parse_contract_classification(request.form)
        except ValueError as e:
            return jsonify({'ok': False, 'blocking': [str(e)], 'warnings': []}), 400

        if mode == 'batch':
            if data.get('procurement_data_sheet_id'):
                return jsonify({
                    'ok': False,
                    'blocking': ['成交建议生成合同仅支持单份生成'],
                    'warnings': [],
                }), 400
            batch_field_keys = helpers.counterparty_batch_keys(
                fields, request.form.get('batch_field_key', '').strip()
            )
            field_values, input_errors = helpers.prepare_generation_values(
                fields, request.form, allow_empty_keys=batch_field_keys
            )
            if input_errors:
                return jsonify({'ok': False, 'blocking': input_errors, 'warnings': []}), 400
            counterparties_text = request.form.get('batch_counterparties', '').strip()
            counterparties = [c.strip() for c in counterparties_text.split('\n') if c.strip()]
            if len(counterparties) > MAX_BATCH_CONTRACTS:
                return jsonify({
                    'ok': False,
                    'blocking': [f'批量生成每次不能超过 {MAX_BATCH_CONTRACTS} 份合同'],
                    'warnings': [],
                }), 400
            if any(len(c) > MAX_COUNTERPARTY_LENGTH for c in counterparties):
                return jsonify({
                    'ok': False,
                    'blocking': [f'对方单位名称不能超过 {MAX_COUNTERPARTY_LENGTH} 个字符'],
                    'warnings': [],
                }), 400
            payload = generation_preflight_service.build_batch_preflight(
                tpl, fields, field_values, classification, counterparties,
                batch_field_keys, generate_pdf=generate_pdf,
            )
            status = 200 if payload['ok'] else 400
            return jsonify(payload), status

        field_values, input_errors = helpers.prepare_generation_values(fields, request.form)
        if input_errors:
            return jsonify({'ok': False, 'blocking': input_errors, 'warnings': []}), 400
        payload = generation_preflight_service.build_single_preflight(
            tpl, fields, field_values, classification, generate_pdf=generate_pdf,
        )
        status = 200 if payload['ok'] else 400
        return jsonify(payload), status

    @bp.route('/generate-batch', methods=['POST'])
    def generate_batch():
        sid = session.get('sid')
        if not sid:
            return '会话已过期，请重新选择模板', 400

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return '会话已过期，请重新选择模板', 400

        if data.get('procurement_data_sheet_id'):
            return '成交建议生成合同仅支持单份生成', 400

        tpl_path = helpers.template_path_from_session(data)
        if not tpl_path:
            return '找不到模板信息', 400

        try:
            tpl = template_def.TemplateDef.load(tpl_path)
        except Exception:
            return '加载模板失败', 500

        tpl_name = data.get('template_name', '') or tpl.name
        fields = tpl.data.get('fields', [])

        batch_field_keys = helpers.counterparty_batch_keys(
            fields, request.form.get('batch_field_key', '').strip()
        )
        if not batch_field_keys:
            return '未能识别对方单位字段，请在"字段变量名"中手动指定', 400

        field_values, input_errors = helpers.prepare_generation_values(
            fields, request.form, allow_empty_keys=batch_field_keys
        )
        if input_errors:
            return '\n'.join(input_errors), 400

        try:
            classification = helpers.parse_contract_classification(request.form)
        except ValueError as e:
            return safe_error(e, '批生成合同分类解析')


        counterparties_text = request.form.get('batch_counterparties', '').strip()
        counterparties = [c.strip() for c in counterparties_text.split('\n') if c.strip()]
        if not counterparties:
            return '请至少输入一个对方单位', 400
        if len(counterparties) > MAX_BATCH_CONTRACTS:
            return f'批量生成每次不能超过 {MAX_BATCH_CONTRACTS} 份合同', 400
        if any(len(c) > MAX_COUNTERPARTY_LENGTH for c in counterparties):
            return f'对方单位名称不能超过 {MAX_COUNTERPARTY_LENGTH} 个字符', 400

        source_docx = tpl.data.get('source_docx', '')
        try:
            template_path = helpers.safe_uploaded_docx_path(source_docx) if source_docx else ''
        except ValueError as e:
            return safe_file_error(e, '批生成获取DOCX路径失败')

        zip_path = os.path.join(helpers.OUTPUT_FOLDER, f'{sid}_{uuid.uuid4().hex[:8]}_batch.zip')
        gen_errors = []
        success_count = 0
        batch_contract_number_keys = helpers.contract_number_keys(fields)
        generation_service = current_app.extensions['contract_tool'].contract_generation
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, counterparty in enumerate(counterparties):
                batch_values = deepcopy(field_values)
                for batch_field_key in batch_field_keys:
                    batch_values[batch_field_key] = counterparty
                for number_key in batch_contract_number_keys:
                    base_number = str(field_values.get(number_key) or '').strip()
                    if base_number:
                        batch_values[number_key] = f'{base_number}-{idx + 1:03d}'
                batch_calc_errors = helpers.recalculate_scalar_fields(fields, batch_values)
                if batch_calc_errors:
                    gen_errors.extend(f'{counterparty}: {error}' for error in batch_calc_errors)
                    continue

                suffix = helpers.safe_filename_part(counterparty, f'contract_{idx + 1}')[:30]
                out_path = os.path.join(helpers.OUTPUT_FOLDER, f'{sid}_batch_{idx}_{suffix}.docx')

                source_id = data.get('source_id')
                linked_project_id = (
                    int(data['source_project_id']) if data.get('source_project_id') else None
                )
                link = ProcurementLink(
                    project_id=linked_project_id,
                    source_type=data.get('source_type') or 'direct_contract',
                    source_id=int(source_id) if source_id else None,
                ) if linked_project_id is not None else None
                try:
                    result = generation_service.generate(
                        ContractGenerationRequest(
                            template=tpl,
                            fields=fields,
                            field_values=batch_values,
                            source_docx=template_path,
                            output_path=out_path,
                            classification=classification,
                            link=link,
                        )
                    )
                    contract_id = result.contract_id
                    out_path = result.output_path
                    linked_project_previous_status = result.previous_project_status
                except DocumentGenerationError as e:
                    details = e.errors or ['合同生成失败']
                    gen_errors.extend(f'{counterparty}: {detail}' for detail in details)
                    continue
                except ValidationError:
                    gen_errors.append(f'{counterparty}: 台账入账失败')
                    continue
                except ProcurementLinkError:
                    gen_errors.append(f'{counterparty}: 采购项目关联失败')
                    continue
                except Exception as e:
                    get_logger().error(
                        'Batch generation transaction failed for %s: %s',
                        counterparty, e, exc_info=True,
                    )
                    gen_errors.append(f'{counterparty}: 合同生成失败')
                    continue

                archive_name = (
                    f'{idx + 1:03d}_'
                    f'{helpers.safe_filename_part(counterparty, f"contract_{idx + 1}")}_合同.docx'
                )
                try:
                    zf.write(out_path, archive_name)
                    success_count += 1
                except Exception as e:
                    get_logger().error('Batch ZIP write failed for contract %s: %s', contract_id, e, exc_info=True)
                    gen_errors.append(f'{counterparty}: ZIP 写入失败')
                    if linked_project_id is not None:
                        try:
                            import procurement_store
                            procurement_store.remove_contract_ref(
                                linked_project_id, contract_id,
                                restore_status=linked_project_previous_status,
                            )
                        except Exception:
                            get_logger().error(
                                'Batch rollback failed to remove procurement ref for contract %s',
                                contract_id,
                                exc_info=True,
                            )
                    _discard_generated_contract(contract_id, out_path)

        if success_count == 0:
            try:
                os.remove(zip_path)
            except OSError:
                pass
            return '批量合同生成失败：\n' + '\n'.join(gen_errors[:20]), 500

        download_name = f'{tpl_name}_批量合同_{success_count}份.zip' if tpl_name else f'批量合同_{success_count}份.zip'
        response = send_file(
            zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/zip',
        )
        if gen_errors:
            response.headers['X-Generation-Errors'] = quote(
                '; '.join(gen_errors[:5]), safe=''
            )
        return response

    @bp.route('/contracts')
    def contract_ledger():
        q = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        view_mode = request.args.get('view', 'list').strip()
        if view_mode not in {'list', 'project'}:
            view_mode = 'list'
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        result = ledger_store.list_contracts(q=q, status=status, page=page)

        # 项目维度分组只在项目进度视图读取，避免列表页承担额外查询。
        project_groups = (
            ledger_store.list_project_grouped_contracts(q=q, status=status)
            if view_mode == 'project' else []
        )

        return render_template(
            'contracts.html',
            contracts=result['rows'],
            contract_ids=[row['id'] for row in result['rows']],
            project_groups=project_groups,
            view_mode=view_mode,
            q=q,
            status=status,
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
        )

    @bp.route('/contracts/export')
    def contract_export():
        q = request.args.get('q', '').strip()
        status = request.args.get('status', '').strip()
        contracts = ledger_store.iter_contracts(q=q, status=status, batch_size=500)
        filename = f'contracts_{date.today().strftime("%Y%m%d")}_{uuid.uuid4().hex[:8]}.xlsx'
        output_path = os.path.join(helpers.OUTPUT_FOLDER, filename)
        xlsx_exporter.export_contracts(
            output_path, contracts, title='合同台账', streaming=True
        )
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'合同台账_{date.today().strftime("%Y%m%d")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @bp.route('/contracts/batch-delete', methods=['POST'])
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

    @bp.route('/contracts/batch-status', methods=['POST'])
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

    @bp.route('/contracts/trash')
    def contract_trash():
        """回收站 — 已软删除合同（SQL 层分页，避免全量加载）"""
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        result = ledger_store.list_contracts(page=page, per_page=20, deleted_only=True)
        return render_template(
            'contracts.html',
            contracts=result['rows'],
            contract_ids=[row['id'] for row in result['rows']],
            q='',
            status='',
            view_mode='list',
            page=result['page'],
            pages=result['pages'],
            total=result['total'],
            trash_mode=True,
        )

    @bp.route('/contracts/<int:contract_id>/soft-delete', methods=['POST'])
    def contract_soft_delete(contract_id):
        """软删除合同（移入回收站）"""
        count = ledger_store.soft_delete_contract(contract_id)
        if count == 0:
            return '合同不存在或已在回收站中', 404
        get_logger().info('Soft deleted contract %d', contract_id)
        return redirect(url_for('contract_ledger'))

    @bp.route('/contracts/<int:contract_id>/restore', methods=['POST'])
    def contract_restore(contract_id):
        """从回收站恢复合同"""
        count = ledger_store.restore_contract(contract_id)
        if count == 0:
            return '合同不在回收站中', 404
        get_logger().info('Restored contract %d from trash', contract_id)
        return redirect(url_for('contract_trash'))

    @bp.route('/contracts/<int:contract_id>/permanent-delete', methods=['POST'])
    def contract_permanent_delete(contract_id):
        """永久删除合同（仅在回收站中可操作）"""
        try:
            count = ledger_store.permanently_delete_contract(contract_id)
        except ValueError as exc:
            return redirect(url_for('contract_detail', contract_id=contract_id, error=str(exc)))
        if count == 0:
            return '合同不在回收站中或无法删除', 404
        get_logger().info('Permanently deleted contract %d', contract_id)
        return redirect(url_for('contract_trash'))

    @bp.route('/contracts/<int:contract_id>')
    def contract_detail(contract_id):
        contract = ledger_store.get_contract(contract_id)
        if not contract:
            return '合同记录不存在', 404
        import procurement_store
        procurement_linked = procurement_store.contract_has_refs(contract_id)
        plans = ledger_store.list_payment_plans(contract_id=contract_id)
        history = ledger_store.get_contract_history(contract_id)
        return render_template(
            'contract_detail.html',
            contract=contract,
            plans=plans,
            history=history,
            project_names=ledger_store.list_project_names(),
            procurement_linked=procurement_linked,
            error=request.args.get('error', ''),
        )

    @bp.route('/contracts/<int:contract_id>/download')
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

    @bp.route('/contracts/<int:contract_id>/download-pdf')
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
        except FileNotFoundError as e:
            get_logger().warning('PDF 导出失败-文件未找到 (contract %d): %s', contract_id, e)
            return 'PDF 导出失败。提示：安装 LibreOffice（免费）即可导出 PDF。\n下载地址：https://www.libreoffice.org', 400
        except RuntimeError as e:
            get_logger().warning('PDF 导出失败 (contract %d): %s', contract_id, e)
            return 'PDF 导出失败。\n\n提示：安装 LibreOffice（免费）即可导出 PDF。\n下载地址：https://www.libreoffice.org', 400
        except Exception as e:
            get_logger().error('PDF 导出异常 (contract %d): %s', contract_id, e, exc_info=True)
            return GENERIC_ERROR, 500
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'{safe_base}.pdf',
            mimetype='application/pdf',
        )

    @bp.route('/contracts/<int:contract_id>/update', methods=['POST'])
    def contract_update(contract_id):
        if not ledger_store.get_contract(contract_id):
            return '合同记录不存在', 404
        new_status = request.form.get('status', 'draft').strip() or 'draft'
        if new_status not in {'draft', 'signed', 'active', 'completed', 'void'}:
            return '无效的状态值', 400
        try:
            classification = helpers.parse_contract_classification(request.form)
            ledger_store.update_contract(contract_id, {
                'contract_no': limit_text(request.form.get('contract_no', '').strip(), 80),
                'title': limit_text(request.form.get('title', '').strip(), 200) or '未命名合同',
                'counterparty': limit_text(request.form.get('counterparty', '').strip(), MAX_COUNTERPARTY_LENGTH),
                'amount': helpers.float_or_none(request.form.get('amount')),
                'sign_date': helpers.normalize_date(request.form.get('sign_date')) or '',
                'expiry_date': helpers.normalize_date(request.form.get('expiry_date')) or '',
                'owner': limit_text(request.form.get('owner', '').strip(), 60),
                'status': new_status,
                **classification,
            })
        except ValueError as e:
            return safe_error(e, '合同更新失败')
        return redirect(url_for('contract_detail', contract_id=contract_id))

    app.register_blueprint(bp)
