"""Shared helpers: session, path helpers, and autostart.

Path variables (UPLOAD_FOLDER, BASE_DIR, etc.) are set by app.py at startup.

Most business logic has been moved to dedicated sub-modules:
  utils.constants           → 枚举常量（CONTRACT_STATUS_LABELS 等）
  utils.field_utils         → 字段键/解析/标记检测/表格规范化
  utils.generation_utils    → 计算/合同摘要/台账/批量/付款辅助
  utils.keyword_maps        → 中文字段关键词 → 业务语义映射
  utils.money               → 金额（分↔元）统一转换
  utils.autostart           → Windows 自启动管理

------ 废弃提示 ------
本模块的重导出（re-export）函数仅为向后兼容保留。
新代码请直接从子模块导入，例如：
  from utils.field_utils import detect_markers, normalize_date
  from utils.generation_utils import generate_docx_document
  from utils.money import from_minor, to_minor
  from utils.keyword_maps import find_scalar_semantic
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import template_def

from utils.security import path_within, safe_join_file
from utils.labels import (  # noqa: F401  # 兼容重导出
    CONTRACT_STATUS_LABELS,
    CONFIRM_STATUS_LABELS,
    PAYMENT_STATUS_LABELS,
    CONFIDENCE_LABELS,
    PAYMENT_PARSE_STATUS_LABELS,
    PAYMENT_REASON_LABELS,
    PAYMENT_AMOUNT_BASIS_LABELS,
    PROCUREMENT_STATUS_LABELS,
    PROCUREMENT_METHOD_LABELS,
    PROCUREMENT_STAGE_ORDER,
    PROCUREMENT_STAGE_LABELS,
    PROCUREMENT_STAGE_STATUS_LABELS,
    CLARIFICATION_STATUS_LABELS,
    QUOTE_STATUS_LABELS,
    QUOTE_IMPORT_STATUS_LABELS,
)
# ── Re-export from sub-modules for backward compatibility ──
# 新代码请直接从 utils.xxx 导入，而非通过 helpers 间接引用
from utils.field_utils import (  # noqa: F401,F811  # 有意重导出
    field_key_from_label, unique_key, safe_col_key,
    safe_filename_part, parse_number, normalize_date,
    to_calc_number, float_or_none, int_or_none, normalize_number_field_value,
    detect_markers, filter_table_rows,
    normalize_table_columns, apply_submitted_table_columns,
    parse_submitted_field_values,
)
from utils.generation_utils import (  # noqa: F401,F811
    calc_context, recalculate_scalar_fields, recalculate_table_fields,
    prepare_generation_values,
    infer_contract_summary, parse_contract_classification,
    create_ledger_record, docx_write_order,
    generate_docx_document,
    counterparty_batch_keys, contract_number_keys, next_month_ym, next_month_range,
    has_payment_content, can_bulk_confirm_payment,
    validate_template_source_bindings,
)
# ── Re-export from autostart module ──
from utils.autostart import (  # noqa: F401,F811
    autostart_status, enable_autostart, disable_autostart,
    AUTOSTART_TASK_NAME, AUTOSTART_LAUNCHER_NAME,
    AUTOSTART_LEGACY_LAUNCHER_NAMES,
)

# ── Paths set by app.py at startup ──
UPLOAD_FOLDER = None
OUTPUT_FOLDER = None
SESSION_FOLDER = None
BASE_DIR = None


# ═══════════════════════════════════════════════════════
#  Session helpers
# ═══════════════════════════════════════════════════════

def save_session_data(sid: str, data: dict[str, Any]) -> None:
    if SESSION_FOLDER is None:
        raise RuntimeError('SESSION_FOLDER 未初始化，请先调用 init_runtime()')
    path = safe_join_file(SESSION_FOLDER, f'{sid}.json', allowed_ext={'.json'})
    tmp = path + f'.tmp-{uuid.uuid4().hex}'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            logging.getLogger('contract_tool').debug(
                '会话暂存文件已不存在: %s', tmp
            )


def load_session_data(sid: str) -> dict[str, Any]:
    if SESSION_FOLDER is None:
        raise RuntimeError('SESSION_FOLDER 未初始化，请先调用 init_runtime()')
    path = safe_join_file(SESSION_FOLDER, f'{sid}.json', allowed_ext={'.json'})
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════
#  Path helpers
# ═══════════════════════════════════════════════════════

def safe_uploaded_docx_path(filename: str) -> str:
    if UPLOAD_FOLDER is None:
        raise RuntimeError('UPLOAD_FOLDER 未初始化，请先调用 init_runtime()')
    return safe_join_file(UPLOAD_FOLDER, filename, allowed_ext={'.docx'})


def safe_template_path(name: str) -> str:
    filename = os.path.basename(name or '')
    if not filename.endswith('.contract-template'):
        raise ValueError('模板文件名无效')
    return safe_join_file(template_def.TEMPLATES_DIR, filename, allowed_ext={'.contract-template'})


def validate_stored_docx(filename: str) -> str:
    if not filename:
        return ''
    path = safe_uploaded_docx_path(filename)
    if not os.path.isfile(path):
        raise ValueError('模板源文件不存在')
    return os.path.basename(filename)


def template_path_from_session(data: dict[str, Any]) -> str:
    template_path_data = data.get('template_path', '')
    if template_path_data:
        path = os.path.abspath(template_path_data)
        if path_within(template_def.TEMPLATES_DIR, path) and os.path.exists(path):
            return path

    template_filename = data.get('template_filename', '')
    if template_filename:
        try:
            path = safe_template_path(template_filename)
        except ValueError:
            return ''
        if os.path.exists(path):
            return path
    return ''
