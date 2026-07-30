"""Deprecated compatibility facade for historical helper imports.

New code must import from the owning module directly.  These re-exports are
scheduled for removal after 2026-12-31:

* field parsing and normalization: :mod:`utils.field_utils`
* generation helpers: :mod:`utils.generation_utils`
* labels: :mod:`utils.labels`
* autostart: :mod:`utils.autostart`
* session persistence: :mod:`utils.session_store`
* template/upload paths: :mod:`utils.template_paths`

The legacy path attributes are dynamically resolved from the immutable
``RuntimePaths`` object.  ``runtime.context.apply_runtime_context`` no longer
mutates this module.
"""

from __future__ import annotations

from typing import Any

from runtime.app_state import app_state
from utils.autostart import (  # noqa: F401
    AUTOSTART_LAUNCHER_NAME,
    AUTOSTART_LEGACY_LAUNCHER_NAMES,
    AUTOSTART_TASK_NAME,
    autostart_status,
    disable_autostart,
    enable_autostart,
)
from utils.field_utils import (  # noqa: F401
    apply_submitted_table_columns,
    detect_markers,
    field_key_from_label,
    filter_table_rows,
    float_or_none,
    int_or_none,
    normalize_date,
    normalize_number_field_value,
    normalize_table_columns,
    parse_number,
    parse_submitted_field_values,
    safe_col_key,
    safe_filename_part,
    to_calc_number,
    unique_key,
)
from utils.generation_utils import (  # noqa: F401
    calc_context,
    can_bulk_confirm_payment,
    contract_number_keys,
    counterparty_batch_keys,
    create_ledger_record,
    docx_write_order,
    generate_docx_document,
    has_payment_content,
    infer_contract_summary,
    next_month_range,
    next_month_ym,
    parse_contract_classification,
    prepare_generation_values,
    recalculate_scalar_fields,
    recalculate_table_fields,
    validate_template_source_bindings,
)
from utils.labels import (  # noqa: F401
    CLARIFICATION_STATUS_LABELS,
    CONFIDENCE_LABELS,
    CONFIRM_STATUS_LABELS,
    CONTRACT_STATUS_LABELS,
    PAYMENT_AMOUNT_BASIS_LABELS,
    PAYMENT_PARSE_STATUS_LABELS,
    PAYMENT_REASON_LABELS,
    PAYMENT_STATUS_LABELS,
    PROCUREMENT_METHOD_LABELS,
    PROCUREMENT_STAGE_LABELS,
    PROCUREMENT_STAGE_ORDER,
    PROCUREMENT_STAGE_STATUS_LABELS,
    PROCUREMENT_STATUS_LABELS,
    QUOTE_IMPORT_STATUS_LABELS,
    QUOTE_STATUS_LABELS,
)
from utils.security import path_within  # noqa: F401
from utils.session_store import (
    load_session_data as _load_session_data,
    save_session_data as _save_session_data,
)
from utils.template_paths import (
    safe_template_path as _safe_template_path,
    safe_uploaded_docx_path as _safe_uploaded_docx_path,
    template_path_from_session as _template_path_from_session,
    validate_stored_docx as _validate_stored_docx,
)


def save_session_data(sid: str, data: dict[str, Any]) -> None:
    return _save_session_data(sid, data, app_state.paths)


def load_session_data(sid: str) -> dict[str, Any]:
    return _load_session_data(sid, app_state.paths)


def safe_uploaded_docx_path(filename: str) -> str:
    return _safe_uploaded_docx_path(filename, app_state.paths)


def safe_template_path(name: str) -> str:
    return _safe_template_path(name, app_state.paths)


def validate_stored_docx(filename: str) -> str:
    return _validate_stored_docx(filename, app_state.paths)


def template_path_from_session(data: dict[str, Any]) -> str:
    return _template_path_from_session(data, app_state.paths)


_LEGACY_PATH_ATTRIBUTES = {
    'UPLOAD_FOLDER': 'uploads_dir',
    'OUTPUT_FOLDER': 'output_dir',
    'SESSION_FOLDER': 'sessions_dir',
    'BASE_DIR': 'base_dir',
}


def __getattr__(name: str):
    """Resolve legacy read-only path names without module-level copies."""
    property_name = _LEGACY_PATH_ATTRIBUTES.get(name)
    if property_name is None:
        raise AttributeError(name)
    return getattr(app_state, property_name)
