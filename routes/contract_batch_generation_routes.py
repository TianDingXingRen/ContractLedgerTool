"""HTTP adapter for batch contract generation."""

from __future__ import annotations

import json
from urllib.parse import quote

from flask import current_app, request, send_file, session

import template_def
from runtime.flask_paths import current_runtime_paths
from services.contract_batch_generation_service import (
    BatchGenerationCommand,
    BatchGenerationFailure,
    generate_batch_archive,
)
from utils.errors import safe_error, safe_file_error
from utils.generation_utils import (
    counterparty_batch_keys,
    parse_contract_classification,
    prepare_generation_values,
)
from utils.security import MAX_BATCH_CONTRACTS, MAX_COUNTERPARTY_LENGTH
from utils.session_store import load_session_data
from utils.template_paths import safe_uploaded_docx_path, template_path_from_session


def _parse_counterparties():
    counterparties = [
        item.strip()
        for item in request.form.get('batch_counterparties', '').strip().split('\n')
        if item.strip()
    ]
    if not counterparties:
        return None, '请至少输入一个对方单位'
    if len(counterparties) > MAX_BATCH_CONTRACTS:
        return None, f'批量生成每次不能超过 {MAX_BATCH_CONTRACTS} 份合同'
    if any(len(item) > MAX_COUNTERPARTY_LENGTH for item in counterparties):
        return None, f'对方单位名称不能超过 {MAX_COUNTERPARTY_LENGTH} 个字符'
    return counterparties, None


def generate_batch():
    sid = session.get('sid')
    if not sid:
        return '会话已过期，请重新选择模板', 400
    paths = current_runtime_paths()
    try:
        data = load_session_data(sid, paths)
    except (FileNotFoundError, json.JSONDecodeError):
        return '会话已过期，请重新选择模板', 400
    if data.get('procurement_data_sheet_id'):
        return '成交建议生成合同仅支持单份生成', 400

    template_path = template_path_from_session(data, paths)
    if not template_path:
        return '找不到模板信息', 400
    try:
        template = template_def.TemplateDef.load(template_path)
    except Exception:
        return '加载模板失败', 500
    fields = template.data.get('fields', [])
    batch_field_keys = counterparty_batch_keys(
        fields,
        request.form.get('batch_field_key', '').strip(),
    )
    if not batch_field_keys:
        return '未能识别对方单位字段，请在"字段变量名"中手动指定', 400
    field_values, input_errors = prepare_generation_values(
        fields,
        request.form,
        allow_empty_keys=batch_field_keys,
    )
    if input_errors:
        return '\n'.join(input_errors), 400
    try:
        classification = parse_contract_classification(request.form)
    except ValueError as exc:
        return safe_error(exc, '批生成合同分类解析')
    counterparties, counterparty_error = _parse_counterparties()
    if counterparty_error:
        return counterparty_error, 400

    source_docx = template.data.get('source_docx', '')
    try:
        source_path = (
            safe_uploaded_docx_path(source_docx, paths) if source_docx else ''
        )
    except ValueError as exc:
        return safe_file_error(exc, '批生成获取DOCX路径失败')
    source_id = data.get('source_id')
    try:
        result = generate_batch_archive(
            BatchGenerationCommand(
                sid=sid,
                template=template,
                fields=fields,
                field_values=field_values,
                classification=classification,
                counterparties=counterparties,
                batch_field_keys=batch_field_keys,
                source_docx=source_path,
                output_dir=str(paths.output_dir),
                generation_service=(
                    current_app.extensions['contract_tool'].contract_generation
                ),
                template_name=data.get('template_name', '') or template.name,
                source_project_id=(
                    int(data['source_project_id'])
                    if data.get('source_project_id')
                    else None
                ),
                source_type=data.get('source_type') or 'direct_contract',
                source_id=int(source_id) if source_id else None,
            )
        )
    except BatchGenerationFailure as exc:
        return exc.public_message, 500

    response = send_file(
        result.zip_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype='application/zip',
    )
    if result.errors:
        response.headers['X-Generation-Errors'] = quote(
            '; '.join(result.errors[:5]),
            safe='',
        )
    return response


def register_contract_batch_generation_routes(bp):
    bp.add_url_rule(
        '/generate-batch',
        endpoint='generate_batch',
        view_func=generate_batch,
        methods=['POST'],
    )
