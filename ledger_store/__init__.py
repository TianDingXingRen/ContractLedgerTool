"""Local storage for contract ledger and payment plans."""

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

from utils.logger import get_logger
from utils.security import path_within as _path_within
from utils.constants import (
    ContractStatus, PaymentStatus, ConfirmStatus, ConfidenceLevel,
)
from . import dashboard_queries
from . import list_queries
from . import project_reports
from .schema import LEDGER_SCHEMA_SQL, MIGRATIONS, SCHEMA_VERSION_SQL

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'contracts.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

# 所有允许的状态值（从 Enum 自动导出）
CONTRACT_STATUSES = {s.value for s in ContractStatus}
PAYMENT_TYPES = {'conditional', 'fixed_date'}
CONFIRM_STATUSES = {s.value for s in ConfirmStatus}
PAYMENT_STATUSES = {s.value for s in PaymentStatus}
CONFIDENCE_LEVELS = {c.value for c in ConfidenceLevel}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _validate_choice(value, allowed, label):
    if value is None or value == '':
        return value
    if value not in allowed:
        raise ValueError(f'{label}无效: {value}')
    return value


@contextmanager
def get_conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(LEDGER_SCHEMA_SQL)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(SCHEMA_VERSION_SQL)
    # 确保迁移在 init 后立即执行
    run_migrations()


# ── Migrations ──

def _deduplicate_contract_numbers(conn):
    """迁移唯一索引前，为历史重复编号生成可追溯的新编号。"""
    duplicates = conn.execute(
        """
        SELECT contract_no
        FROM contracts
        WHERE contract_no IS NOT NULL AND TRIM(contract_no) != ''
        GROUP BY contract_no
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    now = _now()
    for duplicate in duplicates:
        contract_no = duplicate[0]
        rows = conn.execute(
            'SELECT id FROM contracts WHERE contract_no = ? ORDER BY id',
            (contract_no,),
        ).fetchall()
        for row in rows[1:]:
            contract_id = row[0]
            new_no = f'{contract_no}-DUP-{contract_id}'
            suffix = 1
            while conn.execute(
                'SELECT 1 FROM contracts WHERE contract_no = ? AND id != ?',
                (new_no, contract_id),
            ).fetchone():
                suffix += 1
                new_no = f'{contract_no}-DUP-{contract_id}-{suffix}'
            conn.execute(
                'UPDATE contracts SET contract_no = ?, updated_at = ? WHERE id = ?',
                (new_no, now, contract_id),
            )
            conn.execute(
                """INSERT INTO contract_history
                   (contract_id, field, old_value, new_value, changed_at)
                   VALUES (?, 'contract_no', ?, ?, ?)""",
                (contract_id, contract_no, new_no, now),
            )


def run_migrations():
    # 先读取当前版本（只读，不需要事务保护）
    with get_conn() as conn:
        cur = conn.execute('SELECT MAX(version) FROM schema_version')
        row = cur.fetchone()
        current = row[0] if row and row[0] is not None else 0

    # 每个迁移版本使用独立事务，避免后续版本失败时回滚已成功的迁移
    for version, forward_sql, rollback_sql in MIGRATIONS:
        if version <= current:
            continue
        with get_conn() as conn:
            try:
                if version == 8:
                    _deduplicate_contract_numbers(conn)
                conn.execute(forward_sql)
            except sqlite3.OperationalError as e:
                # 新 init_db 已在 CREATE TABLE 中包含该列，跳过重复添加
                if 'duplicate column name' in str(e).lower() or 'already exists' in str(e).lower():
                    get_logger().info('迁移 v%d 列已存在（来自 init_db），跳过', version)
                else:
                    raise
            except Exception as e:
                get_logger().error('数据库迁移 v%d 失败: %s', version, e)
                if rollback_sql:
                    try:
                        conn.execute(rollback_sql)
                        get_logger().warning('已回滚迁移 v%d', version)
                    except Exception as rb_e:
                        get_logger().error('回滚迁移 v%d 失败: %s', version, rb_e)
                raise
            conn.execute(
                'INSERT INTO schema_version (version, applied_at) VALUES (?, ?)',
                (version, _now()),
            )


def close_connections():
    """Checkpoint WAL to prevent data loss on unclean shutdown."""
    if not os.path.isfile(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.close()
    except Exception:
        get_logger().warning('WAL checkpoint 失败', exc_info=True)


# ── Backup ──

def get_all_docx_paths():
    """获取所有合同的 docx_path 列表（轻量查询，仅返回路径字段）。
    用于文件清理时保护台账引用的文件不被删除。
    """
    if not os.path.isfile(DB_PATH):
        return []
    try:
        with get_conn() as conn:
            rows = conn.execute(
                'SELECT docx_path FROM contracts WHERE docx_path IS NOT NULL AND docx_path != \'\''
            ).fetchall()
        return [row[0] for row in rows]
    except Exception:
        get_logger().warning('无法查询合同 docx 路径', exc_info=True)
        return []


def _check_db_integrity(quick=True):
    """数据库完整性检查。quick=True 使用 quick_check（快速），False 使用 integrity_check（彻底）。"""
    if not os.path.isfile(DB_PATH):
        return False
    pragma = 'PRAGMA quick_check' if quick else 'PRAGMA integrity_check'
    try:
        with get_conn() as conn:
            row = conn.execute(pragma).fetchone()
            return row is not None and row[0] == 'ok'
    except Exception:
        return False


def backup_database(max_backups=7):
    """使用 SQLite backup API 原子备份数据库到 backups/ 目录。

    保留最近 N 份不同日期的备份。同一天只保留一份。
    备份前执行 integrity_check（更彻底），修复时用 restore 的 quick_check 做快速校验。
    """
    if not os.path.exists(DB_PATH):
        return None
    if not _check_db_integrity(quick=False):
        get_logger().warning('数据库完整性检查失败，跳过备份')
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = date.today().strftime('%Y-%m-%d')
    backup_path = os.path.join(BACKUP_DIR, f'contracts_{today}.db')
    if not os.path.exists(backup_path):
        # 使用 SQLite online backup API（原子、一致、不阻塞写入）
        src = sqlite3.connect(DB_PATH)
        try:
            src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            dst = sqlite3.connect(backup_path)
            try:
                src.backup(dst)
            finally:
                dst.close()
        except Exception:
            get_logger().warning('SQLite backup API 失败，回退到文件复制', exc_info=True)
            # 回退：必须在 backup API 失败时仍尝试复制
            try:
                shutil.copy2(DB_PATH, backup_path)
            except Exception:
                get_logger().error('数据库备份完全失败', exc_info=True)
                return None
        finally:
            src.close()
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')],
        reverse=True,
    )
    for old in backups[max_backups:]:
        os.remove(os.path.join(BACKUP_DIR, old))
    return backup_path


def list_backups():
    """List database backups newest first."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    rows = []
    for fname in os.listdir(BACKUP_DIR):
        if not fname.endswith('.db'):
            continue
        path = os.path.abspath(os.path.join(BACKUP_DIR, fname))
        if not _path_within(BACKUP_DIR, path):
            continue
        stat = os.stat(path)
        rows.append({
            'filename': fname,
            'path': path,
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        })
    rows.sort(key=lambda item: (item['mtime'], item['filename']), reverse=True)
    return rows


def create_backup(label='manual'):
    """Create a timestamped database backup using SQLite backup API (atomic)."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError('数据库文件不存在')
    os.makedirs(BACKUP_DIR, exist_ok=True)
    safe_label = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in str(label or 'manual'))[:32]
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup_path = os.path.abspath(os.path.join(BACKUP_DIR, f'contracts_{stamp}_{safe_label}.db'))
    if not _path_within(BACKUP_DIR, backup_path):
        raise ValueError('备份路径无效')
    # 使用 SQLite backup API（原子、一致、不阻塞写入）
    src = sqlite3.connect(DB_PATH)
    try:
        src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        dst = sqlite3.connect(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    except Exception:
        get_logger().warning('SQLite backup API 失败，回退到文件复制', exc_info=True)
        try:
            shutil.copy2(DB_PATH, backup_path)
        except Exception:
            get_logger().error('数据库手动备份完全失败', exc_info=True)
            raise
    finally:
        src.close()
    return {
        'filename': os.path.basename(backup_path),
        'path': backup_path,
        'size': os.path.getsize(backup_path),
    }


def backup_path(filename):
    name = os.path.basename(filename or '')
    if not name.endswith('.db'):
        raise FileNotFoundError('备份文件不存在')
    path = os.path.abspath(os.path.join(BACKUP_DIR, name))
    if not _path_within(BACKUP_DIR, path) or not os.path.isfile(path):
        raise FileNotFoundError('备份文件不存在')
    return path


def restore_backup(filename):
    """Restore a database backup. The current DB is backed up before replacement.
    Validates the source file before overwriting."""
    src = backup_path(filename)
    src_conn = None
    try:
        src_conn = sqlite3.connect(src)
        row = src_conn.execute('PRAGMA quick_check').fetchone()
        if row is None or row[0] != 'ok':
            raise ValueError(f'备份文件校验失败: {row[0] if row else "无法读取"}')
    except sqlite3.DatabaseError as e:
        raise ValueError(f'备份文件不是有效的 SQLite 数据库: {e}')
    finally:
        if src_conn:
            src_conn.close()
    if os.path.exists(DB_PATH):
        create_backup('before_restore')
    os.makedirs(DATA_DIR, exist_ok=True)
    shutil.copy2(src, DB_PATH)
    return DB_PATH


def row_to_dict(row):
    return dict(row) if row is not None else None


def create_contract(summary, field_values, docx_path):
    """创建合同记录（不含付款计划），返回 contract_id。

    内部委托 create_contract_with_plans 以复用 INSERT 逻辑，
    避免两处 SQL 重复导致维护时遗漏同步。
    """
    contract_id, _ = create_contract_with_plans(summary, field_values, docx_path, [])
    return contract_id


def create_contract_with_plans(summary, field_values, docx_path, plans):
    """在单个事务中创建合同并批量插入付款计划，保证原子性。

    返回 (contract_id, plan_count)。
    """
    now = _now()
    status = _validate_choice(summary.get('status') or 'draft', CONTRACT_STATUSES, '合同状态')
    values_json = json.dumps(field_values or {}, ensure_ascii=False, default=str)
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO contracts (
                    contract_no, title, counterparty, amount, sign_date, owner,
                    status, template_name, docx_path, values_json, expiry_date,
                    project_name, coverage_start, coverage_end, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.get('contract_no'),
                    summary.get('title') or '未命名合同',
                    summary.get('counterparty'),
                    summary.get('amount'),
                    summary.get('sign_date'),
                    summary.get('owner'),
                    status,
                    summary.get('template_name'),
                    docx_path,
                    values_json,
                    summary.get('expiry_date') or '',
                    summary.get('project_name') or '',
                    summary.get('coverage_start'),
                    summary.get('coverage_end'),
                    now,
                    now,
                ),
            )
            contract_id = cur.lastrowid
            plan_count = 0
            if plans:
                for plan in plans:
                    _insert_payment_plan_impl(conn, contract_id, plan)
                    plan_count += 1
            return contract_id, plan_count
    except sqlite3.IntegrityError as e:
        if 'contract_no' in str(e).lower() or 'idx_contracts_contract_no_unique' in str(e).lower():
            raise ValueError('合同编号已存在') from e
        raise


def update_contract(contract_id, data):
    allowed = [
        'contract_no', 'title', 'counterparty', 'amount', 'sign_date',
        'expiry_date', 'owner', 'status', 'project_name',
        'coverage_start', 'coverage_end',
    ]
    assignments = []
    values = []
    for key in allowed:
        if key in data:
            if key == 'status':
                data[key] = _validate_choice(data[key], CONTRACT_STATUSES, '合同状态')
            assignments.append(f'{key} = ?')
            values.append(data[key])
    if not assignments:
        return
    now = _now()
    assignments.append('updated_at = ?')
    values.append(now)
    values.append(contract_id)
    try:
        with get_conn() as conn:
            # 在同一事务中读取旧值并执行更新，避免 TOCTOU 竞态
            old_row = conn.execute(
                'SELECT * FROM contracts WHERE id = ?', (contract_id,)
            ).fetchone()
            old_contract = row_to_dict(old_row)
            conn.execute(
                f"UPDATE contracts SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            if old_contract:
                for key in allowed:
                    if key not in data:
                        continue
                    old_val = str(old_contract.get(key) or '')
                    new_val = str(data[key] or '')
                    if old_val != new_val:
                        conn.execute(
                            """INSERT INTO contract_history
                               (contract_id, field, old_value, new_value, changed_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            (contract_id, key, old_val, new_val, now),
                        )
    except sqlite3.IntegrityError as e:
        if 'contract_no' in str(e).lower() or 'idx_contracts_contract_no_unique' in str(e).lower():
            raise ValueError('合同编号已存在') from e
        raise


def get_contract(contract_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM contracts WHERE id = ?', (contract_id,)).fetchone()
    return row_to_dict(row)


def list_contracts(q='', status='', page=1, per_page=20, include_deleted=False, deleted_only=False):
    """列出合同台账，支持关键词搜索和状态筛选。

    使用 EXISTS 子查询替代 LEFT JOIN 以避免支付计划行膨胀。
    默认排除已软删除的合同。
    deleted_only=True 时只返回回收站中的合同（分页在 SQL 层完成）。
    """
    return list_queries.list_contracts(
        get_conn, row_to_dict, q, status, page, per_page,
        include_deleted=include_deleted, deleted_only=deleted_only,
    )


def list_project_names():
    """Return existing project names, most recently updated first."""
    return project_reports.list_project_names(get_conn)


def list_project_grouped_contracts(q='', status=''):
    """返回按 project_name 分组的合同列表，仅查询有项目名称的合同。

    用于合同台账页面的项目进度视图，避免全量加载所有合同。
    返回 [(project_name, [contract_dict, ...]), ...]。
    """
    return project_reports.list_project_grouped_contracts(get_conn, row_to_dict, q, status)


def get_project_progress_stats():
    """Summarize contract signing and payment reach by project.

    Signing progress counts signed/active/completed contracts. Payment-plan
    reach includes non-void plans; paid reach requires a confirmed plan with
    either a positive paid amount or a partial/paid status.
    """
    return project_reports.get_project_progress_stats(get_conn, row_to_dict)


def insert_payment_plan(contract_id, plan):
    """插入单条付款计划（公开接口，使用独立事务）"""
    with get_conn() as conn:
        return _insert_payment_plan_impl(conn, contract_id, plan)


def insert_payment_plans(contract_id, plans):
    """批量插入付款计划 —— 在单个事务内完成，保证原子性。"""
    if not plans:
        return []
    with get_conn() as conn:
        ids = []
        for plan in plans:
            ids.append(_insert_payment_plan_impl(conn, contract_id, plan))
        return ids


def _insert_payment_plan_impl(conn, contract_id, plan):
    """在已有连接中插入单条付款计划（由 insert_payment_plans 调用）"""
    plan = _normalize_payment_consistency(plan)
    now = _now()
    payment_type = _validate_choice(plan.get('payment_type') or 'conditional', PAYMENT_TYPES, '付款类型')
    confidence = _validate_choice(plan.get('confidence') or 'low', CONFIDENCE_LEVELS, '置信度')
    confirm_status = _validate_choice(plan.get('confirm_status') or 'pending', CONFIRM_STATUSES, '确认状态')
    payment_status = _validate_choice(plan.get('payment_status') or 'unpaid', PAYMENT_STATUSES, '付款状态')
    cur = conn.execute(
        """
        INSERT INTO payment_plans (
            contract_id, phase_name, payment_type, trigger_event, trigger_days,
            expected_trigger_date, due_date, ratio, due_amount, paid_amount,
            paid_date, condition_text, source_text, confidence, confirm_status,
            payment_status, remark, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contract_id,
            plan.get('phase_name'),
            payment_type,
            plan.get('trigger_event'),
            plan.get('trigger_days'),
            plan.get('expected_trigger_date'),
            plan.get('due_date'),
            plan.get('ratio'),
            plan.get('due_amount'),
            plan.get('paid_amount') or 0,
            plan.get('paid_date'),
            plan.get('condition_text'),
            plan.get('source_text'),
            confidence,
            confirm_status,
            payment_status,
            plan.get('remark'),
            now,
            now,
        ),
    )
    return cur.lastrowid


def _normalize_payment_consistency(plan):
    """校验金额/日期关系，并由金额统一推导付款状态。"""
    row = dict(plan)
    due_amount = row.get('due_amount')
    paid_amount = row.get('paid_amount') or 0
    if due_amount is not None and due_amount < 0:
        raise ValueError('应付金额不能为负数')
    if paid_amount < 0:
        raise ValueError('已付金额不能为负数')
    if due_amount is not None and paid_amount > due_amount:
        raise ValueError('已付金额不能大于应付金额')
    if paid_amount > 0 and not str(row.get('paid_date') or '').strip():
        raise ValueError('填写已付金额后必须填写实付日期')

    if paid_amount <= 0:
        row['payment_status'] = 'unpaid'
        row['paid_date'] = ''
    elif due_amount is not None and paid_amount >= due_amount:
        row['payment_status'] = 'paid'
    else:
        row['payment_status'] = 'partial'
    return row


def save_payment_plan_changes(contract_id, changes):
    """在一个事务中保存付款计划的新增、修改和删除。"""
    with get_conn() as conn:
        contract = conn.execute('SELECT id FROM contracts WHERE id = ?', (contract_id,)).fetchone()
        if not contract:
            raise ValueError('合同记录不存在')

        for change in changes:
            plan_id = change.get('id')
            if change.get('delete'):
                if plan_id:
                    cur = conn.execute(
                        'DELETE FROM payment_plans WHERE id = ? AND contract_id = ?',
                        (plan_id, contract_id),
                    )
                    if cur.rowcount == 0:
                        raise ValueError('付款计划不存在或不属于当前合同')
                continue

            row = _normalize_payment_consistency(change.get('data') or {})
            if plan_id:
                allowed = [
                    'phase_name', 'payment_type', 'trigger_event', 'trigger_days',
                    'expected_trigger_date', 'due_date', 'ratio', 'due_amount',
                    'paid_amount', 'paid_date', 'condition_text', 'source_text',
                    'confidence', 'confirm_status', 'payment_status', 'remark',
                ]
                validators = {
                    'payment_type': (PAYMENT_TYPES, '付款类型'),
                    'confidence': (CONFIDENCE_LEVELS, '置信度'),
                    'confirm_status': (CONFIRM_STATUSES, '确认状态'),
                    'payment_status': (PAYMENT_STATUSES, '付款状态'),
                }
                assignments = []
                values = []
                for key in allowed:
                    if key not in row:
                        continue
                    if key in validators:
                        row[key] = _validate_choice(row[key], *validators[key])
                    assignments.append(f'{key} = ?')
                    values.append(row[key])
                assignments.append('updated_at = ?')
                values.extend([_now(), plan_id, contract_id])
                cur = conn.execute(
                    f"UPDATE payment_plans SET {', '.join(assignments)} "
                    "WHERE id = ? AND contract_id = ?",
                    values,
                )
                if cur.rowcount == 0:
                    raise ValueError('付款计划不存在或不属于当前合同')
            else:
                _insert_payment_plan_impl(conn, contract_id, row)


def list_payment_plans(contract_id=None, confirm_status='', payment_status='',
                       start_date='', end_date='', project_name='', page=0,
                       per_page=20):
    return list_queries.list_payment_plans(
        get_conn, row_to_dict, contract_id=contract_id,
        confirm_status=confirm_status, payment_status=payment_status,
        start_date=start_date, end_date=end_date, project_name=project_name,
        page=page, per_page=per_page,
    )


def update_payment_plan(plan_id, data, contract_id=None):
    allowed = [
        'phase_name', 'payment_type', 'trigger_event', 'trigger_days',
        'expected_trigger_date', 'due_date', 'ratio', 'due_amount',
        'paid_amount', 'paid_date', 'condition_text', 'source_text',
        'confidence', 'confirm_status', 'payment_status', 'remark',
    ]
    validators = {
        'payment_type': (PAYMENT_TYPES, '付款类型'),
        'confidence': (CONFIDENCE_LEVELS, '置信度'),
        'confirm_status': (CONFIRM_STATUSES, '确认状态'),
        'payment_status': (PAYMENT_STATUSES, '付款状态'),
    }
    if not any(key in data for key in allowed):
        return
    with get_conn() as conn:
        where = 'id = ?'
        lookup_values = [plan_id]
        if contract_id is not None:
            where += ' AND contract_id = ?'
            lookup_values.append(contract_id)
        existing = conn.execute(
            f'SELECT * FROM payment_plans WHERE {where}', lookup_values
        ).fetchone()
        if not existing:
            return 0
        merged = dict(existing)
        merged.update({key: data[key] for key in allowed if key in data})
        merged = _normalize_payment_consistency(merged)
        assignments = []
        values = []
        for key in allowed:
            if key not in data and key not in {'payment_status', 'paid_date'}:
                continue
            if key in validators:
                merged[key] = _validate_choice(merged[key], *validators[key])
            assignments.append(f'{key} = ?')
            values.append(merged[key])
        assignments.append('updated_at = ?')
        values.append(_now())
        values.extend(lookup_values)
        cur = conn.execute(
            f"UPDATE payment_plans SET {', '.join(assignments)} WHERE {where}",
            values,
        )
        return cur.rowcount


def batch_confirm_plans(plan_ids, contract_id=None):
    """在单个事务中批量确认付款计划，保证原子性。"""
    if not plan_ids:
        return 0
    now = _now()
    with get_conn() as conn:
        count = 0
        for plan_id in plan_ids:
            where = 'id = ? AND confirm_status = ?'
            params = [plan_id, 'pending']
            if contract_id is not None:
                where += ' AND contract_id = ?'
                params.append(contract_id)
            cur = conn.execute(
                f"UPDATE payment_plans SET confirm_status = 'confirmed', updated_at = ? WHERE {where}",
                [now] + params,
            )
            count += cur.rowcount
        return count


def delete_payment_plan(plan_id, contract_id=None):
    sql = 'DELETE FROM payment_plans WHERE id = ?'
    params = [plan_id]
    if contract_id is not None:
        sql += ' AND contract_id = ?'
        params.append(contract_id)
    with get_conn() as conn:
        conn.execute(sql, params)


def next_month_payment_plans(start_date, end_date):
    return dashboard_queries.next_month_payment_plans(
        get_conn, row_to_dict, start_date, end_date
    )


def get_contract_stats():
    """合约统计：总数、各状态数、金额合计（排除已软删除的合同）"""
    return dashboard_queries.get_contract_stats(get_conn)


def get_payment_stats():
    """付款统计：应付/已付/未付金额（排除已软删除的合同）"""
    return dashboard_queries.get_payment_stats(get_conn)


def get_monthly_payments(year, month):
    """指定月份应付款统计：笔数和金额（排除已软删除的合同）"""
    return dashboard_queries.get_monthly_payments(get_conn, year, month)


def get_expiring_contracts(days=30):
    """获取 N 天内到期的合同（已签订/履行中，未软删除）"""
    return dashboard_queries.get_expiring_contracts(get_conn, row_to_dict, days)


def get_due_soon_payments(days=7):
    """N 天内到期、已确认、未付清的付款计划"""
    return dashboard_queries.get_due_soon_payments(get_conn, row_to_dict, days)


def get_recent_contracts(limit=5):
    """最近 N 的合同（排除已软删除）"""
    return dashboard_queries.get_recent_contracts(get_conn, row_to_dict, limit)


# ── Soft delete / trash ──

def soft_delete_contract(contract_id):
    """软删除合同（设置 deleted_at 标记，不实际删除数据）"""
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE contracts SET deleted_at = ?, updated_at = ? WHERE id = ? AND (deleted_at = '' OR deleted_at IS NULL)",
            (now, now, contract_id),
        )
        if cur.rowcount:
            conn.execute(
                """INSERT INTO contract_history
                   (contract_id, field, old_value, new_value, changed_at)
                   VALUES (?, 'deleted_at', '', ?, ?)""",
                (contract_id, now, now),
            )
        return cur.rowcount


def restore_contract(contract_id):
    """从回收站恢复软删除的合同"""
    now = _now()
    with get_conn() as conn:
        old = conn.execute('SELECT deleted_at FROM contracts WHERE id = ?', (contract_id,)).fetchone()
        cur = conn.execute(
            "UPDATE contracts SET deleted_at = '', updated_at = ? WHERE id = ? AND deleted_at != '' AND deleted_at IS NOT NULL",
            (now, contract_id),
        )
        if cur.rowcount:
            conn.execute(
                """INSERT INTO contract_history
                   (contract_id, field, old_value, new_value, changed_at)
                   VALUES (?, 'deleted_at', ?, '', ?)""",
                (contract_id, old[0] if old else '', now),
            )
        return cur.rowcount


def permanently_delete_contract(contract_id):
    """永久删除合同及其关联数据（仅限已在回收站中的合同）"""
    with get_conn() as conn:
        # 先确认合同已被软删除
        row = conn.execute(
            "SELECT id FROM contracts WHERE id = ? AND deleted_at != '' AND deleted_at IS NOT NULL",
            (contract_id,),
        ).fetchone()
        if not row:
            return 0
        conn.execute("DELETE FROM contract_history WHERE contract_id = ?", (contract_id,))
        conn.execute("DELETE FROM payment_plans WHERE contract_id = ?", (contract_id,))
        cur = conn.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        return cur.rowcount


# ── Batch operations ──

def batch_delete_contracts(ids):
    """软删除多个合同（设置 deleted_at 标记，保留数据）"""
    if not ids:
        return 0
    now = _now()
    with get_conn() as conn:
        placeholders = ','.join('?' for _ in ids)
        cur = conn.execute(
            f"UPDATE contracts SET deleted_at = ?, updated_at = ? WHERE id IN ({placeholders}) AND (deleted_at = '' OR deleted_at IS NULL)",
            [now, now] + ids,
        )
        return cur.rowcount


def batch_update_status(ids, status):
    """Batch update contract status."""
    if not ids:
        return 0
    status = _validate_choice(status, CONTRACT_STATUSES, '合同状态')
    now = _now()
    with get_conn() as conn:
        placeholders = ','.join('?' for _ in ids)
        old_rows = conn.execute(
            f"SELECT id, status FROM contracts WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        cur = conn.execute(
            f"UPDATE contracts SET status = ?, updated_at = ? WHERE id IN ({placeholders})",
            [status, now] + ids,
        )
        for row in old_rows:
            if row['status'] == status:
                continue
            conn.execute(
                """INSERT INTO contract_history
                   (contract_id, field, old_value, new_value, changed_at)
                   VALUES (?, 'status', ?, ?, ?)""",
                (row['id'], row['status'], status, now),
            )
        return cur.rowcount


# ── Contract history ──

def get_contract_history(contract_id):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM contract_history WHERE contract_id = ? ORDER BY changed_at DESC',
            (contract_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]
