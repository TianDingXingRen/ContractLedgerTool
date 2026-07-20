"""Handover data packages and checklist exports."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import date, datetime

import ledger_store
import template_def
import xlsx_exporter
from services.handover_archive import (
    add_directory as _add_directory,
    add_file as _add_file,
    copy_database as _copy_database,
    member_allowed,
    normalize_archive_name as _normalize_archive_name,
    safe_label as _safe_label,
    sha256_zip_member as _sha256_zip_member,
    validate_sqlite_file as _validate_sqlite_file,
)
from utils import helpers
from utils.labels import (
    CONTRACT_STATUS_LABELS,
    CONFIRM_STATUS_LABELS,
    PAYMENT_STATUS_LABELS,
    PROCUREMENT_METHOD_LABELS,
    PROCUREMENT_STATUS_LABELS,
)
from utils.logger import get_logger
from utils.security import path_within


PACKAGE_TYPE = 'contract_tool_full_backup'
MANIFEST_NAME = 'manifest.json'
PACKAGE_DIR_NAME = 'packages'


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _base_dir():
    return os.path.abspath(helpers.BASE_DIR or os.path.dirname(ledger_store.DATA_DIR))


def _dir_or_default(value, name):
    return os.path.abspath(value or os.path.join(_base_dir(), name))


def _package_dir():
    path = os.path.abspath(os.path.join(ledger_store.BACKUP_DIR, PACKAGE_DIR_NAME))
    os.makedirs(path, exist_ok=True)
    return path


def _excel_defaults_dir():
    return os.path.abspath(os.path.join(ledger_store.DATA_DIR, 'excel_bill_defaults'))


def _restore_targets():
    return {
        'config.json': {
            'kind': 'file',
            'path': os.path.abspath(os.path.join(_base_dir(), 'config.json')),
        },
        'data/contracts.db': {
            'kind': 'file',
            'path': os.path.abspath(ledger_store.DB_PATH),
        },
        'data/excel_bill_defaults': {
            'kind': 'dir',
            'path': _excel_defaults_dir(),
        },
        'uploads': {
            'kind': 'dir',
            'path': _dir_or_default(helpers.UPLOAD_FOLDER, 'uploads'),
        },
        'templates': {
            'kind': 'dir',
            'path': os.path.abspath(template_def.TEMPLATES_DIR),
        },
        'output': {
            'kind': 'dir',
            'path': _dir_or_default(helpers.OUTPUT_FOLDER, 'output'),
        },
    }


def _member_allowed(name):
    return member_allowed(name, _restore_targets(), MANIFEST_NAME)


def _read_version():
    version_path = os.path.join(_base_dir(), 'version.txt')
    try:
        with open(version_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def create_full_backup_package(label='handover'):
    """Create a complete handover ZIP package and return file metadata."""
    packages_dir = _package_dir()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    safe_label = _safe_label(label)
    target_path = os.path.abspath(os.path.join(
        packages_dir, f'handover_full_{stamp}_{safe_label}.zip'
    ))
    if not path_within(packages_dir, target_path):
        raise ValueError('完整数据包路径无效')

    temp_db = os.path.join(packages_dir, f'.package_db_{uuid.uuid4().hex}.db')
    records = []
    roots = []
    try:
        _copy_database(ledger_store.DB_PATH, temp_db)
        _validate_sqlite_file(temp_db)
        with zipfile.ZipFile(target_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            config_path = os.path.join(_base_dir(), 'config.json')
            roots.append({
                'path': 'config.json',
                'kind': 'file',
                'present': _add_file(zf, config_path, 'config.json', records),
            })
            roots.append({
                'path': 'data/contracts.db',
                'kind': 'file',
                'present': _add_file(zf, temp_db, 'data/contracts.db', records),
            })
            roots.append(_add_directory(zf, _excel_defaults_dir(), 'data/excel_bill_defaults', records))
            roots.append(_add_directory(zf, _dir_or_default(helpers.UPLOAD_FOLDER, 'uploads'), 'uploads', records))
            roots.append(_add_directory(zf, template_def.TEMPLATES_DIR, 'templates', records))
            roots.append(_add_directory(zf, _dir_or_default(helpers.OUTPUT_FOLDER, 'output'), 'output', records))
            manifest = {
                'package_type': PACKAGE_TYPE,
                'manifest_version': 1,
                'created_at': _now(),
                'app': {'version': _read_version()},
                'database': {
                    'archive_path': 'data/contracts.db',
                    'integrity_ok': True,
                },
                'roots': roots,
                'files': records,
            }
            zf.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
            )
    finally:
        try:
            os.remove(temp_db)
        except OSError:
            get_logger().warning('无法删除完整备份临时数据库: %s', temp_db, exc_info=True)

    stat = os.stat(target_path)
    return {
        'filename': os.path.basename(target_path),
        'path': target_path,
        'size': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        'file_count': len(records),
    }


def list_full_backup_packages():
    packages_dir = _package_dir()
    rows = []
    for filename in os.listdir(packages_dir):
        if not filename.lower().endswith('.zip'):
            continue
        path = os.path.abspath(os.path.join(packages_dir, filename))
        if not path_within(packages_dir, path) or not os.path.isfile(path):
            continue
        stat = os.stat(path)
        valid = True
        created_at = ''
        try:
            manifest = read_package_manifest(path)
            created_at = manifest.get('created_at', '')
        except Exception:
            valid = False
        rows.append({
            'filename': filename,
            'path': path,
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'created_at': created_at,
            'valid': valid,
        })
    rows.sort(key=lambda item: (item['mtime'], item['filename']), reverse=True)
    return rows


def full_package_path(filename):
    name = os.path.basename(filename or '')
    if not name.lower().endswith('.zip'):
        raise FileNotFoundError('完整数据包不存在')
    path = os.path.abspath(os.path.join(_package_dir(), name))
    if not path_within(_package_dir(), path) or not os.path.isfile(path):
        raise FileNotFoundError('完整数据包不存在')
    return path


def read_package_manifest(path):
    with zipfile.ZipFile(path, 'r') as zf:
        with zf.open(MANIFEST_NAME) as f:
            manifest = json.loads(f.read().decode('utf-8'))
    if manifest.get('package_type') != PACKAGE_TYPE:
        raise ValueError('不是本工具生成的完整数据包')
    return manifest


def validate_full_backup_package(path):
    if not zipfile.is_zipfile(path):
        raise ValueError('完整数据包不是有效 ZIP 文件')
    with zipfile.ZipFile(path, 'r') as zf:
        infos = {_normalize_archive_name(info.filename): info for info in zf.infolist()}
        names = set(infos)
        if MANIFEST_NAME not in names:
            raise ValueError('完整数据包缺少 manifest.json')
        for info in zf.infolist():
            normalized = _normalize_archive_name(info.filename)
            if not _member_allowed(normalized):
                raise ValueError('完整数据包包含不允许恢复的路径')
        manifest = read_package_manifest(path)
        manifest_files = {}
        for item in manifest.get('files') or []:
            file_path = _normalize_archive_name(item.get('path'))
            manifest_files[file_path] = item
        for name, info in infos.items():
            if name == MANIFEST_NAME or info.is_dir():
                continue
            if name not in manifest_files:
                raise ValueError('完整数据包文件清单不完整')
        for name, item in manifest_files.items():
            info = infos.get(name)
            if info is None or info.is_dir():
                raise ValueError('完整数据包文件缺失')
            expected_sha = str(item.get('sha256') or '').lower()
            if expected_sha and _sha256_zip_member(zf, name) != expected_sha:
                raise ValueError('完整数据包文件校验失败')
        if 'data/contracts.db' not in names:
            raise ValueError('完整数据包缺少数据库文件')
        temp_dir = tempfile.mkdtemp(prefix='validate_package_', dir=_package_dir())
        temp_db = os.path.join(temp_dir, 'contracts.db')
        try:
            with zf.open('data/contracts.db') as src, open(temp_db, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            _validate_sqlite_file(temp_db)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return manifest


def upload_full_backup_package(file_storage):
    filename = os.path.basename(getattr(file_storage, 'filename', '') or '')
    if not filename:
        raise ValueError('请选择要上传的完整数据包')
    if not filename.lower().endswith('.zip'):
        raise ValueError('完整数据包必须是 ZIP 文件')

    packages_dir = _package_dir()
    temp_path = os.path.abspath(os.path.join(packages_dir, f'.upload_{uuid.uuid4().hex}.zip'))
    file_storage.save(temp_path)
    try:
        validate_full_backup_package(temp_path)
        stem = os.path.splitext(filename)[0]
        target_name = f'uploaded_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{_safe_label(stem)}.zip'
        target_path = os.path.abspath(os.path.join(packages_dir, target_name))
        if not path_within(packages_dir, target_path):
            raise ValueError('上传文件名无效')
        shutil.move(temp_path, target_path)
        stat = os.stat(target_path)
        return {
            'filename': os.path.basename(target_path),
            'path': target_path,
            'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            get_logger().warning('无法删除完整备份临时包: %s', temp_path, exc_info=True)
        raise


def _extract_zip_safe(path, target_dir):
    target_dir = os.path.abspath(target_dir)
    with zipfile.ZipFile(path, 'r') as zf:
        for info in zf.infolist():
            normalized = _normalize_archive_name(info.filename)
            dest = os.path.abspath(os.path.join(target_dir, normalized.replace('/', os.sep)))
            if not path_within(target_dir, dest):
                raise ValueError('完整数据包内文件路径无效')
            if info.is_dir():
                os.makedirs(dest, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(info) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)


def _replace_from_staging(staging_dir, originals_dir):
    moved_originals = []
    copied_targets = []
    targets = _restore_targets()
    try:
        for archive_root, spec in targets.items():
            stage_path = os.path.join(staging_dir, archive_root.replace('/', os.sep))
            if not os.path.exists(stage_path):
                continue
            target_path = spec['path']
            backup_path = os.path.join(originals_dir, archive_root.replace('/', os.sep))
            if os.path.exists(target_path):
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.move(target_path, backup_path)
                moved_originals.append((target_path, backup_path))
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            if spec['kind'] == 'dir':
                if not os.path.isdir(stage_path):
                    raise ValueError(f'完整数据包路径类型不匹配: {archive_root}')
                shutil.copytree(stage_path, target_path)
            else:
                if not os.path.isfile(stage_path):
                    raise ValueError(f'完整数据包路径类型不匹配: {archive_root}')
                shutil.copy2(stage_path, target_path)
            copied_targets.append(target_path)
    except Exception:
        for target_path in reversed(copied_targets):
            if os.path.isdir(target_path):
                shutil.rmtree(target_path, ignore_errors=True)
            else:
                try:
                    os.remove(target_path)
                except OSError:
                    get_logger().error(
                        '恢复回滚时无法删除已复制文件: %s', target_path, exc_info=True,
                    )
        for target_path, backup_path in reversed(moved_originals):
            if os.path.exists(target_path):
                if os.path.isdir(target_path):
                    shutil.rmtree(target_path, ignore_errors=True)
                else:
                    try:
                        os.remove(target_path)
                    except OSError:
                        get_logger().error(
                            '恢复回滚时无法清理目标文件: %s', target_path, exc_info=True,
                        )
            if os.path.exists(backup_path):
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.move(backup_path, target_path)
        raise


def restore_full_backup_package(filename):
    path = full_package_path(filename)
    manifest = validate_full_backup_package(path)
    rollback = create_full_backup_package(label='before_full_restore')

    staging_dir = tempfile.mkdtemp(prefix='restore_stage_', dir=_package_dir())
    originals_dir = tempfile.mkdtemp(prefix='restore_original_', dir=_package_dir())
    try:
        ledger_store.close_connections()
        _extract_zip_safe(path, staging_dir)
        _replace_from_staging(staging_dir, originals_dir)
        ledger_store.init_db()
        try:
            import procurement_store
            procurement_store.init_db()
        except Exception:
            get_logger().warning('恢复完整数据包后初始化采购表失败', exc_info=True)
        return {'rollback': rollback, 'manifest': manifest}
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
        shutil.rmtree(originals_dir, ignore_errors=True)


def list_handover_owners(limit=200):
    with ledger_store.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT owner FROM (
                SELECT DISTINCT TRIM(COALESCE(owner, '')) AS owner FROM contracts
                UNION
                SELECT DISTINCT TRIM(COALESCE(owner, '')) AS owner FROM procurement_projects
            )
            WHERE owner != ''
            ORDER BY owner
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [row[0] for row in rows]


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _fetch_dicts(cursor, batch_size=500):
    """Consume a large SQLite result in bounded batches."""
    result = []
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            return result
        result.extend(dict(row) for row in rows)


def _amount(value):
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0


def _minor_to_amount(value):
    try:
        return round(int(value or 0) / 100, 2)
    except (TypeError, ValueError):
        return 0


def _rel_path(path):
    if not path:
        return ''
    raw = str(path)
    if not os.path.isabs(raw):
        return raw.replace('\\', '/')
    base = _base_dir()
    if path_within(base, raw):
        return os.path.relpath(raw, base).replace(os.sep, '/')
    return raw


def _contract_filters(include_closed):
    clauses = ["TRIM(COALESCE(c.owner, '')) = ?", "(c.deleted_at = '' OR c.deleted_at IS NULL)"]
    if not include_closed:
        clauses.append("c.status NOT IN ('completed', 'void')")
    return clauses


def _payment_filters(include_closed):
    clauses = ["TRIM(COALESCE(c.owner, '')) = ?", "(c.deleted_at = '' OR c.deleted_at IS NULL)"]
    if not include_closed:
        clauses.extend([
            "c.status NOT IN ('completed', 'void')",
            "p.confirm_status != 'void'",
            "p.payment_status != 'paid'",
        ])
    return clauses


def _project_filters(include_closed):
    clauses = ["TRIM(COALESCE(p.owner, '')) = ?"]
    if not include_closed:
        clauses.append("p.status NOT IN ('contract_created', 'archived')")
    return clauses


def build_handover_data(owner, include_closed=False, today=None):
    owner = str(owner or '').strip()
    if not owner:
        raise ValueError('请输入离职员工姓名')
    today = today or date.today()
    today_str = today.strftime('%Y-%m-%d')

    with ledger_store.get_conn() as conn:
        contract_where = ' AND '.join(_contract_filters(include_closed))
        contracts = _fetch_dicts(conn.execute(
            f"""
            SELECT c.*,
                   COUNT(p.id) AS plan_count,
                   COALESCE(SUM(p.due_amount_minor), 0) AS due_total_minor,
                   COALESCE(SUM(p.paid_amount_minor), 0) AS paid_total_minor,
                   SUM(CASE WHEN p.payment_status != 'paid' AND p.confirm_status != 'void'
                            THEN 1 ELSE 0 END) AS unpaid_plan_count
            FROM contracts c
            LEFT JOIN payment_plans p ON p.contract_id = c.id
            WHERE {contract_where}
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id DESC
            """,
            (owner,),
        ))

        payment_where = ' AND '.join(_payment_filters(include_closed))
        payments = _fetch_dicts(conn.execute(
            f"""
            SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty,
                   c.owner, c.project_name
            FROM payment_plans p
            JOIN contracts c ON c.id = p.contract_id
            WHERE {payment_where}
            ORDER BY COALESCE(p.due_date, ''), p.id
            """,
            (owner,),
        ))

        project_where = ' AND '.join(_project_filters(include_closed))
        projects = _fetch_dicts(conn.execute(
            f"""
            SELECT p.*,
                   (SELECT COUNT(*) FROM project_items i WHERE i.project_id = p.id) AS item_count,
                   (SELECT COUNT(*) FROM project_suppliers s WHERE s.project_id = p.id) AS supplier_count,
                   (SELECT COUNT(*) FROM supplier_quotes q
                    WHERE q.project_id = p.id AND q.status = 'confirmed') AS quote_count,
                   (SELECT COUNT(*) FROM project_files f WHERE f.project_id = p.id) AS file_count,
                   (SELECT COUNT(*) FROM clarification_questions cq
                    WHERE cq.project_id = p.id AND cq.status NOT IN ('closed')) AS pending_clarification_count
            FROM procurement_projects p
            WHERE {project_where}
            ORDER BY p.updated_at DESC, p.id DESC
            """,
            (owner,),
        ))

        file_where = ' AND '.join(_project_filters(include_closed))
        project_files = _fetch_dicts(conn.execute(
            f"""
            SELECT f.*, p.project_no, p.project_name
            FROM project_files f
            JOIN procurement_projects p ON p.id = f.project_id
            WHERE {file_where}
            ORDER BY f.created_at DESC, f.id DESC
            """,
            (owner,),
        ))

    for row in contracts:
        row['status_label'] = CONTRACT_STATUS_LABELS.get(row.get('status'), row.get('status') or '')
        row['amount'] = _minor_to_amount(row.get('amount_minor'))
        row['unpaid_amount'] = round(
            _minor_to_amount(row.get('due_total_minor'))
            - _minor_to_amount(row.get('paid_total_minor')),
            2,
        )
        row['docx_path'] = _rel_path(row.get('docx_path'))

    for row in payments:
        row['confirm_status_label'] = CONFIRM_STATUS_LABELS.get(
            row.get('confirm_status'), row.get('confirm_status') or ''
        )
        row['payment_status_label'] = PAYMENT_STATUS_LABELS.get(
            row.get('payment_status'), row.get('payment_status') or ''
        )
        row['due_amount'] = _minor_to_amount(row.get('due_amount_minor'))
        row['paid_amount'] = _minor_to_amount(row.get('paid_amount_minor'))
        row['unpaid_amount'] = round(row['due_amount'] - row['paid_amount'], 2)

    for row in projects:
        row['status_label'] = PROCUREMENT_STATUS_LABELS.get(row.get('status'), row.get('status') or '')
        row['method_label'] = PROCUREMENT_METHOD_LABELS.get(
            row.get('purchase_method'), row.get('purchase_method') or ''
        )
        row['budget_amount'] = _minor_to_amount(row.get('budget_minor'))
        row['target_price_amount'] = _minor_to_amount(row.get('target_price_minor'))

    file_rows = []
    for contract in contracts:
        if contract.get('docx_path'):
            file_rows.append({
                'source': '合同文件',
                'related_no': contract.get('contract_no') or '',
                'related_name': contract.get('title') or '',
                'file_type': 'docx',
                'original_name': os.path.basename(contract.get('docx_path') or ''),
                'relative_path': contract.get('docx_path') or '',
                'size_bytes': '',
                'created_at': contract.get('updated_at') or '',
            })
    for item in project_files:
        file_rows.append({
            'source': '采购附件',
            'related_no': item.get('project_no') or '',
            'related_name': item.get('project_name') or '',
            'file_type': item.get('file_type') or '',
            'original_name': item.get('original_name') or '',
            'relative_path': item.get('relative_path') or '',
            'size_bytes': item.get('size_bytes') or 0,
            'created_at': item.get('created_at') or '',
        })

    risk_rows = []
    for payment in payments:
        if payment.get('payment_status') == 'paid' or payment.get('confirm_status') == 'void':
            continue
        due_date = payment.get('due_date') or ''
        risk_type = '付款逾期' if due_date and due_date < today_str else '待付款'
        risk_rows.append({
            'risk_type': risk_type,
            'related_no': payment.get('contract_no') or '',
            'related_name': payment.get('contract_title') or '',
            'detail': payment.get('phase_name') or '',
            'amount': payment.get('unpaid_amount') or 0,
            'due_date': due_date,
            'status': payment.get('payment_status_label') or '',
        })
    for project in projects:
        if project.get('status') not in {'contract_created', 'archived'}:
            risk_rows.append({
                'risk_type': '采购未完结',
                'related_no': project.get('project_no') or '',
                'related_name': project.get('project_name') or '',
                'detail': project.get('status_label') or '',
                'amount': '',
                'due_date': '',
                'status': project.get('status_label') or '',
            })
        supplier_count = int(project.get('supplier_count') or 0)
        quote_count = int(project.get('quote_count') or 0)
        if supplier_count and quote_count < supplier_count:
            risk_rows.append({
                'risk_type': '报价不完整',
                'related_no': project.get('project_no') or '',
                'related_name': project.get('project_name') or '',
                'detail': f'供应商 {supplier_count} 家，已确认报价 {quote_count} 份',
                'amount': '',
                'due_date': '',
                'status': project.get('status_label') or '',
            })
        pending = int(project.get('pending_clarification_count') or 0)
        if pending:
            risk_rows.append({
                'risk_type': '澄清未关闭',
                'related_no': project.get('project_no') or '',
                'related_name': project.get('project_name') or '',
                'detail': f'{pending} 条澄清问题未关闭',
                'amount': '',
                'due_date': '',
                'status': project.get('status_label') or '',
            })

    outstanding_total = sum(
        max(payment.get('unpaid_amount') or 0, 0)
        for payment in payments
        if payment.get('payment_status') != 'paid' and payment.get('confirm_status') != 'void'
    )
    active_project_count = sum(
        1 for project in projects
        if project.get('status') not in {'contract_created', 'archived'}
    )
    return {
        'owner': owner,
        'generated_at': _now(),
        'include_closed': bool(include_closed),
        'today': today_str,
        'summary': {
            'contract_count': len(contracts),
            'payment_count': len(payments),
            'project_count': len(projects),
            'file_count': len(file_rows),
            'risk_count': len(risk_rows),
            'outstanding_payment_amount': round(outstanding_total, 2),
            'active_project_count': active_project_count,
        },
        'contracts': contracts,
        'payments': payments,
        'projects': projects,
        'risks': risk_rows,
        'files': file_rows,
    }


def export_handover_checklist(output_dir, owner, include_closed=False):
    data = build_handover_data(owner, include_closed=include_closed)
    os.makedirs(output_dir, exist_ok=True)
    safe_owner = _safe_label(data['owner'], 'employee')
    filename = f'handover_{safe_owner}_{date.today().strftime("%Y%m%d")}_{uuid.uuid4().hex[:8]}.xlsx'
    path = os.path.abspath(os.path.join(output_dir, filename))
    xlsx_exporter.export_handover_checklist(path, data)
    return {
        'path': path,
        'filename': filename,
        'download_name': f'{data["owner"]}_交接清单_{date.today().strftime("%Y%m%d")}.xlsx',
        'summary': data['summary'],
    }
