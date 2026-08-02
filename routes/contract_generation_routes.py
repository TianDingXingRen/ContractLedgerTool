"""HTTP adapters for single-contract generation and preflight."""

from __future__ import annotations

import json
import os
import uuid

from flask import current_app, jsonify, redirect, request, send_file, session, url_for

import template_def
from core.domain_errors import DocumentGenerationError, ProcurementLinkError, ValidationError
from runtime.flask_paths import current_runtime_paths
from services import generation_preflight_service
from services.contract_generation_service import ContractGenerationRequest, ProcurementLink
from utils.errors import GENERIC_GENERATE_ERROR, safe_error, safe_file_error
from utils.generation_utils import (
    counterparty_batch_keys,
    parse_contract_classification,
    prepare_generation_values,
)
from utils.logger import get_logger
from utils.security import MAX_BATCH_CONTRACTS, MAX_COUNTERPARTY_LENGTH
from utils.session_store import load_session_data
from utils.template_paths import safe_uploaded_docx_path, template_path_from_session


def _public_validation_errors(errors):
    """Map internal validation details to a small, user-safe message set."""
    messages = []
    for error in errors:
        detail = str(error)
        if '除数为零' in detail:
            message = '合同公式计算失败：除数为零'
        elif '不能为空' in detail:
            message = '合同必填字段不能为空'
        elif '选项无效' in detail:
            message = '合同字段选项无效'
        elif '公式' in detail:
            message = '合同公式配置或计算失败'
        else:
            message = '合同字段校验失败，请检查填写内容'
        if message not in messages:
            messages.append(message)
    return messages or ['合同字段校验失败，请检查填写内容']


def _procurement_link(data):
    source_id = data.get('source_id')
    if not (data.get('procurement_data_sheet_id') or data.get('source_project_id')):
        return None
    return ProcurementLink(
        data_sheet_id=(
            int(data['procurement_data_sheet_id'])
            if data.get('procurement_data_sheet_id')
            else None
        ),
        project_id=(
            int(data['source_project_id'])
            if data.get('source_project_id')
            else None
        ),
        source_type=data.get('source_type') or 'direct_contract',
        source_id=int(source_id) if source_id else None,
    )


def generate():
    sid = session.get('sid')
    if not sid:
        return redirect(url_for('contracts.index'))
    paths = current_runtime_paths()
    try:
        data = load_session_data(sid, paths)
    except (FileNotFoundError, json.JSONDecodeError):
        return redirect(url_for('contracts.index'))

    template_data_path = template_path_from_session(data, paths)
    if not template_data_path or not os.path.exists(template_data_path):
        return '未找到模板数据，请返回重新选择模板', 400
    template = template_def.TemplateDef.load(template_data_path)
    fields = template.data['fields']
    field_values, input_errors = prepare_generation_values(fields, request.form)
    if input_errors:
        return '\n'.join(input_errors), 400
    try:
        classification = parse_contract_classification(request.form)
    except ValueError as exc:
        return safe_error(exc, '合同分类解析')

    source_docx = template.data.get('source_docx', '')
    source_path = ''
    if source_docx:
        try:
            source_path = safe_uploaded_docx_path(source_docx, paths)
        except ValueError as exc:
            return safe_file_error(exc, '获取DOCX路径失败')
    raw_name = data.get('raw_name', data.get('template_name', '合同'))
    output_name = f'{os.path.splitext(raw_name)[0]}_已生成.docx'
    output_path = os.path.join(
        str(paths.output_dir),
        f'{sid}_{uuid.uuid4().hex[:8]}_output.docx',
    )
    try:
        result = current_app.extensions['contract_tool'].contract_generation.generate(
            ContractGenerationRequest(
                template=template,
                fields=fields,
                field_values=field_values,
                source_docx=source_path,
                output_path=output_path,
                classification=classification,
                link=_procurement_link(data),
            )
        )
    except DocumentGenerationError as exc:
        get_logger().error('合同生成失败: %s', exc.detail)
        return GENERIC_GENERATE_ERROR, 500
    except ValidationError as exc:
        return safe_error(exc, '台账保存失败')
    except ProcurementLinkError as exc:
        return safe_error(exc, '采购项目关联失败', 500)
    except Exception as exc:
        return safe_error(exc, '合同生成事务失败', 500)

    response = send_file(
        result.output_path,
        as_attachment=True,
        download_name=output_name,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    if result.contract_id:
        response.headers['X-Contract-Id'] = str(result.contract_id)
        response.headers['X-Contract-Detail-Url'] = url_for(
            'contracts.contract_detail',
            contract_id=result.contract_id,
        )
    return response


def _batch_preflight(template, fields, data, classification):
    if data.get('procurement_data_sheet_id'):
        return {
            'ok': False,
            'blocking': ['成交建议生成合同仅支持单份生成'],
            'warnings': [],
        }
    batch_field_keys = counterparty_batch_keys(
        fields,
        request.form.get('batch_field_key', '').strip(),
    )
    field_values, input_errors = prepare_generation_values(
        fields,
        request.form,
        allow_empty_keys=batch_field_keys,
    )
    if input_errors:
        return {
            'ok': False,
            'blocking': _public_validation_errors(input_errors),
            'warnings': [],
        }
    counterparties = [
        item.strip()
        for item in request.form.get('batch_counterparties', '').strip().split('\n')
        if item.strip()
    ]
    if len(counterparties) > MAX_BATCH_CONTRACTS:
        return {
            'ok': False,
            'blocking': [f'批量生成每次不能超过 {MAX_BATCH_CONTRACTS} 份合同'],
            'warnings': [],
        }
    if any(len(item) > MAX_COUNTERPARTY_LENGTH for item in counterparties):
        return {
            'ok': False,
            'blocking': [f'对方单位名称不能超过 {MAX_COUNTERPARTY_LENGTH} 个字符'],
            'warnings': [],
        }
    return generation_preflight_service.build_batch_preflight(
        template,
        fields,
        field_values,
        classification,
        counterparties,
        batch_field_keys,
    )


def generate_preflight():
    sid = session.get('sid')
    expired = {'ok': False, 'blocking': ['会话已过期，请重新选择模板'], 'warnings': []}
    if not sid:
        return jsonify(expired), 400
    paths = current_runtime_paths()
    try:
        data = load_session_data(sid, paths)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify(expired), 400
    template_path = template_path_from_session(data, paths)
    if not template_path:
        return jsonify({
            'ok': False,
            'blocking': ['找不到模板信息'],
            'warnings': [],
        }), 400
    try:
        template = template_def.TemplateDef.load(template_path)
    except Exception:
        return jsonify({
            'ok': False,
            'blocking': ['加载模板失败'],
            'warnings': [],
        }), 500

    fields = template.data.get('fields', [])
    try:
        classification = parse_contract_classification(request.form)
    except ValueError:
        return jsonify({
            'ok': False,
            'blocking': ['合同分类信息无效'],
            'warnings': [],
        }), 400
    if request.form.get('_generation_mode', 'single') == 'batch':
        payload = _batch_preflight(
            template,
            fields,
            data,
            classification,
        )
    else:
        field_values, input_errors = prepare_generation_values(fields, request.form)
        if input_errors:
            payload = {
                'ok': False,
                'blocking': _public_validation_errors(input_errors),
                'warnings': [],
            }
        else:
            payload = generation_preflight_service.build_single_preflight(
                template,
                fields,
                field_values,
                classification,
            )
    return jsonify(payload), 200 if payload['ok'] else 400


def register_contract_generation_routes(bp):
    bp.add_url_rule('/generate', endpoint='generate', view_func=generate, methods=['POST'])
    bp.add_url_rule(
        '/generate/preflight',
        endpoint='generate_preflight',
        view_func=generate_preflight,
        methods=['POST'],
    )
