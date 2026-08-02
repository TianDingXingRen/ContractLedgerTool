"""Session and staging workflow for external contract imports."""

from __future__ import annotations

import os
import shutil
import time
import uuid

import ledger_store
from config import config as app_config
from runtime.flask_paths import current_runtime_paths
from services.contract_import_service import ContractImportRequest
from utils.logger import get_logger
from utils.session_store import load_session_data, save_session_data
from utils.security import safe_join_file


class ImportSessionExpired(ValueError):
    """The browser session or staged import is no longer usable."""


class ImportPreviewRejected(ValueError):
    def __init__(self, message, *, duplicate_contract=None, status=400):
        super().__init__(message)
        self.duplicate_contract = duplicate_contract
        self.status = status


class ImportConfirmationRejected(ValueError):
    def __init__(self, message, *, data, duplicate_contract=None):
        super().__init__(message)
        self.data = data
        self.duplicate_contract = duplicate_contract


class ImportConfirmationFailed(RuntimeError):
    def __init__(self, *, data):
        super().__init__('合同导入失败，数据未写入，请重试')
        self.data = data


def _session_file_path(sid):
    return safe_join_file(
        str(current_runtime_paths().sessions_dir),
        f'{sid}.json',
        allowed_ext={'.json'},
    )


def staging_path(data):
    return safe_join_file(
        str(current_runtime_paths().uploads_dir),
        data.get('staging_name', ''),
        allowed_ext={'.docx'},
    )


def _delete_session_file(sid):
    try:
        path = _session_file_path(sid)
        if os.path.isfile(path):
            os.remove(path)
    except (OSError, ValueError):
        get_logger().warning(
            '无法清理合同导入会话 %s', sid, exc_info=True
        )


def discard_import_session(sid):
    """Remove one unconfirmed import session and its staged upload."""
    if not sid:
        return
    try:
        data = load_session_data(sid, current_runtime_paths())
        if (
            data.get('kind') == 'contract_import'
            and not data.get('confirmed_contract_id')
        ):
            staged_file = staging_path(data)
            if os.path.isfile(staged_file):
                os.remove(staged_file)
    except (FileNotFoundError, OSError, ValueError):
        get_logger().info('合同导入暂存会话已不存在: %s', sid)
    _delete_session_file(sid)


def load_import_session(sid, expected_sid):
    if not sid or expected_sid != sid:
        raise ImportSessionExpired('合同导入会话不存在或已过期')
    path = _session_file_path(sid)
    ttl_seconds = max(
        1, int(app_config.SESSION_TTL_HOURS)
    ) * 3600
    if (
        not os.path.isfile(path)
        or os.path.getmtime(path) < time.time() - ttl_seconds
    ):
        discard_import_session(sid)
        raise ImportSessionExpired('合同导入会话不存在或已过期')
    data = load_session_data(sid, current_runtime_paths())
    if data.get('kind') != 'contract_import':
        raise ImportSessionExpired('合同导入会话无效')
    return data


def _remove_staged_file(path, log_message):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        get_logger().warning(log_message, exc_info=True)


def start_import_preview(
    file_stream,
    filename,
    *,
    previous_sid,
    importer,
):
    original_name = os.path.basename(str(filename or ''))[:255]
    if not original_name:
        raise ImportPreviewRejected('请选择 DOCX 合同文件')
    if os.path.splitext(original_name)[1].lower() != '.docx':
        raise ImportPreviewRejected('仅支持 .docx 格式')

    if previous_sid:
        discard_import_session(previous_sid)

    sid = uuid.uuid4().hex
    staging_name = f'contract_import_{sid}.docx'
    staged_file = safe_join_file(
        str(current_runtime_paths().uploads_dir),
        staging_name,
        allowed_ext={'.docx'},
    )
    try:
        with open(staged_file, 'wb') as output:
            shutil.copyfileobj(file_stream, output)
        preview = importer.preview_file(staged_file, original_name)
        save_session_data(
            sid,
            {
                'kind': 'contract_import',
                'staging_name': staging_name,
                'preview': preview.to_dict(),
                'confirmed_contract_id': None,
            },
            current_runtime_paths(),
        )
        return sid
    except ValueError as exc:
        _remove_staged_file(
            staged_file, '合同导入预览失败后无法清理文件'
        )
        contract_id = getattr(exc, 'contract_id', None)
        duplicate = (
            ledger_store.get_contract(contract_id)
            if contract_id
            else None
        )
        raise ImportPreviewRejected(
            str(exc),
            duplicate_contract=duplicate,
            status=409 if duplicate else 400,
        ) from exc
    except Exception as exc:
        _remove_staged_file(
            staged_file, '合同导入解析异常后无法清理文件'
        )
        get_logger().error('合同导入预览失败', exc_info=True)
        raise ImportPreviewRejected(
            '合同解析失败，请确认文件有效后重试'
        ) from exc


def review_import(sid, expected_sid):
    data = load_import_session(sid, expected_sid)
    confirmed_id = data.get('confirmed_contract_id')
    if confirmed_id:
        return data, int(confirmed_id)
    if not os.path.isfile(staging_path(data)):
        raise ImportSessionExpired('暂存合同已过期，请重新上传')
    return data, None


def review_model(
    sid,
    data,
    *,
    submitted_summary=None,
    submitted_plans=None,
    submitted_rules=None,
    duplicate_contract=None,
):
    preview = data['preview']
    diagnostics = {
        item.get('field'): item
        for item in preview.get('diagnostics', [])
        if item.get('field')
    }
    return {
        'sid': sid,
        'preview': preview,
        'summary': submitted_summary
        or preview.get('summary', {}),
        'plans': (
            submitted_plans
            if submitted_plans is not None
            else preview.get('plans', [])
        ),
        'rules': (
            submitted_rules
            if submitted_rules is not None
            else preview.get('rules', [])
        ),
        'diagnostics': diagnostics,
        'project_names': ledger_store.list_project_names(),
        'duplicate_contract': duplicate_contract,
    }


def _mark_confirmed(sid, data, contract_id):
    data['confirmed_contract_id'] = int(contract_id)
    save_session_data(sid, data, current_runtime_paths())


def _duplicate_for_error(exc, preview, summary):
    contract_id = getattr(exc, 'contract_id', None)
    duplicate = (
        ledger_store.get_contract(contract_id)
        if contract_id
        else None
    )
    if duplicate is None:
        duplicate = ledger_store.get_contract_by_source_sha256(
            preview.get('source_sha256')
        )
    if duplicate is None and summary.get('contract_no'):
        duplicate = ledger_store.get_contract_by_contract_no(
            summary['contract_no']
        )
    return duplicate


def confirm_import(
    sid,
    expected_sid,
    *,
    summary,
    plans,
    rules,
    importer,
):
    data = load_import_session(sid, expected_sid)
    confirmed_id = data.get('confirmed_contract_id')
    if confirmed_id:
        return int(confirmed_id)

    preview = data['preview']
    staged_file = staging_path(data)
    if not os.path.isfile(staged_file):
        existing = ledger_store.get_contract_by_source_sha256(
            preview.get('source_sha256')
        )
        if existing:
            _mark_confirmed(sid, data, existing['id'])
            return int(existing['id'])
        raise ImportSessionExpired('暂存合同已过期，请重新上传')

    try:
        if (
            summary.get('contract_no')
            and ledger_store.contract_no_exists(
                summary['contract_no']
            )
        ):
            raise ValueError('合同编号已存在，请修改后再导入')
        result = importer.finalize(
            ContractImportRequest(
                staging_path=staged_file,
                original_filename=preview['original_filename'],
                source_sha256=preview['source_sha256'],
                summary=summary,
                plans=plans,
                rules=rules,
            )
        )
        _mark_confirmed(sid, data, result.contract_id)
        get_logger().info(
            'Imported contract %d from %s with %d payment plan(s)',
            result.contract_id,
            preview['original_filename'],
            result.plan_count,
        )
        return int(result.contract_id)
    except ValueError as exc:
        duplicate = _duplicate_for_error(exc, preview, summary)
        if duplicate and not os.path.isfile(staged_file):
            _mark_confirmed(sid, data, duplicate['id'])
            return int(duplicate['id'])
        raise ImportConfirmationRejected(
            str(exc),
            data=data,
            duplicate_contract=duplicate,
        ) from exc
    except Exception as exc:
        get_logger().error(
            '确认导入合同时发生异常', exc_info=True
        )
        raise ImportConfirmationFailed(data=data) from exc


def cancel_import(sid, expected_sid):
    try:
        load_import_session(sid, expected_sid)
        discard_import_session(sid)
    except (FileNotFoundError, OSError, ValueError):
        get_logger().info('取消合同时暂存会话已不存在: %s', sid)
