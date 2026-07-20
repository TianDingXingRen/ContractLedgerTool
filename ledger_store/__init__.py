"""Local storage for contract ledger and payment plans."""

import json
import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from utils.logger import get_logger
from core.maintenance_gate import maintenance_gate
from utils.constants import (
    ContractStatus, PaymentStatus, ConfirmStatus, ConfidenceLevel,
)
from . import backups as backup_ops
from . import dashboard_queries
from . import document_paths
from . import generation_jobs
from . import list_queries
from . import money_fields
from . import project_reports
from .contract_lifecycle import ContractLifecycleRepository
from .payment_plans import PaymentPlanRepository
from .schema import (
    CURRENT_SCHEMA_VERSION,
    DOCUMENT_PATH_MIGRATION_VERSION,
    FRESH_DATABASE_INDEX_SQL,
    LEDGER_INDEX_SQL,
    LEDGER_TABLE_SQL,
    MIGRATION_BACKFILLS,
    MIGRATIONS,
    SCHEMA_VERSION_SQL,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _data_dir():
    try:
        from runtime.app_state import app_state
        if app_state.is_configured():
            return app_state.data_dir
    except Exception:
        get_logger().debug('读取运行时数据目录失败，回退到默认目录', exc_info=True)
    return os.path.join(BASE_DIR, 'data')


def _db_path():
    try:
        from runtime.app_state import app_state
        if app_state.is_configured():
            return app_state.database_file
    except Exception:
        get_logger().debug('读取运行时数据库路径失败，回退到默认路径', exc_info=True)
    return os.path.join(_data_dir(), 'contracts.db')


def _backup_dir():
    try:
        from runtime.app_state import app_state
        if app_state.is_configured():
            return app_state.backups_dir
    except Exception:
        get_logger().debug('读取运行时备份目录失败，回退到默认目录', exc_info=True)
    return os.path.join(_data_dir(), 'backups')


DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'contracts.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

_ACTIVE_CONNECTION = ContextVar('ledger_active_connection', default=None)

# 所有允许的状态值（从 Enum 自动导出）
CONTRACT_STATUSES = {s.value for s in ContractStatus}
PAYMENT_TYPES = {'conditional', 'fixed_date'}
CONFIRM_STATUSES = {s.value for s in ConfirmStatus}
PAYMENT_STATUSES = {s.value for s in PaymentStatus}
CONFIDENCE_LEVELS = {c.value for c in ConfidenceLevel}

# 可更新的合同字段
CONTRACT_UPDATE_FIELDS = [
    'contract_no', 'title', 'counterparty', 'amount', 'sign_date',
    'expiry_date', 'owner', 'status', 'project_name',
    'coverage_start', 'coverage_end',
]

# 可更新的付款计划字段
PLAN_UPDATE_FIELDS = [
    'phase_name', 'payment_type', 'trigger_event', 'trigger_days',
    'expected_trigger_date', 'due_date', 'ratio', 'due_amount',
    'paid_amount', 'paid_date', 'condition_text', 'source_text',
    'confidence', 'confirm_status', 'payment_status', 'remark',
]

# 付款计划字段对应的校验器
PLAN_FIELD_VALIDATORS = {
    'payment_type': (PAYMENT_TYPES, '付款类型'),
    'confidence': (CONFIDENCE_LEVELS, '置信度'),
    'confirm_status': (CONFIRM_STATUSES, '确认状态'),
    'payment_status': (PAYMENT_STATUSES, '付款状态'),
}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _validate_choice(value, allowed, label):
    if value is None or value == '':
        return value
    if value not in allowed:
        raise ValueError(f'{label}无效: {value}')
    return value


def _runtime_base_dir():
    return document_paths.runtime_base_dir(DATA_DIR, DB_PATH)


def portable_docx_path(path):
    """Return a runtime-relative path when the document belongs to this install."""
    return document_paths.to_portable(path, _runtime_base_dir())


def resolve_docx_path(path):
    """Resolve stored relative paths and rebase legacy absolute output paths."""
    return document_paths.resolve(path, _runtime_base_dir())


def create_generation_job(job_id, output_path, staging_path):
    return generation_jobs.create(
        get_conn, portable_docx_path, job_id, output_path, staging_path
    )


def update_generation_job(job_id, state, **kwargs):
    return generation_jobs.update(get_conn, job_id, state, **kwargs)


def get_generation_job(job_id):
    return generation_jobs.get(get_conn, job_id)


def list_unfinished_generation_jobs():
    return generation_jobs.list_unfinished(get_conn)


def get_generation_job_state_counts():
    return generation_jobs.state_counts(get_conn)


def _amount_pair(value, *, allow_none=True):
    return money_fields.amount_pair(value, allow_none=allow_none)


def _normalize_docx_paths_in_db(conn):
    return document_paths.normalize_contract_paths(conn, _runtime_base_dir())


@contextmanager
def get_conn():
    active = _ACTIVE_CONNECTION.get()
    if active is not None:
        yield active
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 30000')
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
    fresh_database = not os.path.isfile(DB_PATH) or os.path.getsize(DB_PATH) == 0
    with get_conn() as conn:
        conn.executescript(LEDGER_TABLE_SQL)
        _ensure_legacy_contract_columns(conn)
        conn.executescript(LEDGER_INDEX_SQL)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(SCHEMA_VERSION_SQL)
        if fresh_database:
            conn.executescript(FRESH_DATABASE_INDEX_SQL)
            conn.execute(
                'INSERT INTO schema_version (version, applied_at) VALUES (?, ?)',
                (CURRENT_SCHEMA_VERSION, _now()),
            )
            return
    # Existing databases are upgraded only after the compatibility columns and
    # base indexes required by the migration runner are available.
    run_migrations()


# ── Migrations ──

LEGACY_CONTRACT_COLUMNS = {
    'deleted_at': "TEXT DEFAULT ''",
    'expiry_date': "TEXT DEFAULT ''",
    'project_name': "TEXT DEFAULT ''",
    'coverage_start': 'INTEGER',
    'coverage_end': 'INTEGER',
}


def _ensure_legacy_contract_columns(conn):
    """Repair pre-migration contract tables before indexes are created."""
    rows = conn.execute('PRAGMA table_info(contracts)').fetchall()
    existing = {row['name'] if isinstance(row, sqlite3.Row) else row[1] for row in rows}
    for column, definition in LEGACY_CONTRACT_COLUMNS.items():
        if column not in existing:
            conn.execute(f'ALTER TABLE contracts ADD COLUMN {column} {definition}')

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


def get_schema_version():
    """Return the installed ledger schema version without changing the database."""
    if not os.path.isfile(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone()
        if not table:
            return 0
        row = conn.execute('SELECT MAX(version) FROM schema_version').fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        conn.close()


@contextmanager
def read_snapshot():
    """Reuse one query-only SQLite snapshot across nested store calls."""
    active = _ACTIVE_CONNECTION.get()
    if active is not None:
        yield active
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 30000')
    conn.execute('PRAGMA query_only = ON')
    conn.row_factory = sqlite3.Row
    conn.execute('BEGIN')
    token = _ACTIVE_CONNECTION.set(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        _ACTIVE_CONNECTION.reset(token)
        conn.close()


def needs_migration():
    return get_schema_version() < CURRENT_SCHEMA_VERSION


def run_migrations():
    # 先读取当前版本（只读，不需要事务保护）
    with get_conn() as conn:
        cur = conn.execute('SELECT MAX(version) FROM schema_version')
        row = cur.fetchone()
        current = row[0] if row and row[0] is not None else 0

    # 每个迁移版本使用独立事务，避免后续版本失败时回滚已成功的迁移
    for version, forward_sql, _rollback_sql in MIGRATIONS:
        if version <= current:
            continue
        with get_conn() as conn:
            savepoint = f'ledger_migration_v{version}'
            conn.execute(f'SAVEPOINT {savepoint}')
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
                conn.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                conn.execute(f'RELEASE SAVEPOINT {savepoint}')
                get_logger().error('数据库迁移 v%d 失败: %s', version, e)
                raise
            backfill_sql = MIGRATION_BACKFILLS.get(version)
            if backfill_sql:
                conn.execute(backfill_sql)
            if version == DOCUMENT_PATH_MIGRATION_VERSION:
                _normalize_docx_paths_in_db(conn)
            conn.execute(
                'INSERT INTO schema_version (version, applied_at) VALUES (?, ?)',
                (version, _now()),
            )
            conn.execute(f'RELEASE SAVEPOINT {savepoint}')


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
    return [
        resolve_docx_path(path)
        for path in backup_ops.get_all_docx_paths(get_conn, DB_PATH)
    ]


def _check_db_integrity(quick=True):
    return backup_ops.check_db_integrity(get_conn, DB_PATH, quick=quick)


def backup_database(max_backups=7):
    return backup_ops.backup_database(get_conn, DB_PATH, BACKUP_DIR, max_backups=max_backups)


def list_backups():
    return backup_ops.list_backups(BACKUP_DIR)


def create_backup(label='manual'):
    return backup_ops.create_backup(DB_PATH, BACKUP_DIR, label=label)


def backup_path(filename):
    return backup_ops.backup_path(BACKUP_DIR, filename)


def restore_backup(filename):
    import procurement_store

    with maintenance_gate.exclusive():
        close_connections()
        restored, rollback = backup_ops.restore_backup(
            DB_PATH, DATA_DIR, BACKUP_DIR, filename, create_backup
        )
        try:
            init_db()
            procurement_store.init_db()
        except Exception:
            get_logger().error('数据库恢复后初始化失败，正在自动回滚', exc_info=True)
            if rollback and rollback.get('path'):
                close_connections()
                backup_ops.replace_database(DB_PATH, DATA_DIR, rollback['path'])
                init_db()
                procurement_store.init_db()
            raise
        return restored


def row_to_dict(row):
    result = money_fields.with_public_amounts(row)
    if result is None:
        return None
    if 'docx_path' in result:
        result['docx_path'] = resolve_docx_path(result.get('docx_path'))
    return result


_PAYMENT_PLANS = PaymentPlanRepository(
    get_conn=get_conn,
    row_to_dict=row_to_dict,
    now=_now,
    validate_choice=_validate_choice,
    payment_types=PAYMENT_TYPES,
    confidence_levels=CONFIDENCE_LEVELS,
    confirm_statuses=CONFIRM_STATUSES,
    payment_statuses=PAYMENT_STATUSES,
    update_fields=PLAN_UPDATE_FIELDS,
    field_validators=PLAN_FIELD_VALIDATORS,
)


def create_contract(summary, field_values, docx_path):
    """创建合同记录（不含付款计划），返回 contract_id。

    内部委托 create_contract_with_plans 以复用 INSERT 逻辑，
    避免两处 SQL 重复导致维护时遗漏同步。
    """
    contract_id, _ = create_contract_with_plans(summary, field_values, docx_path, [])
    return contract_id


def _create_contract_with_plans_impl(conn, summary, field_values, docx_path, plans):
    now = _now()
    status = _validate_choice(summary.get('status') or 'draft', CONTRACT_STATUSES, '合同状态')
    values_json = json.dumps(field_values or {}, ensure_ascii=False, default=str)
    amount_minor, amount = _amount_pair(summary.get('amount'))
    stored_docx_path = portable_docx_path(docx_path)
    cur = conn.execute(
        """
        INSERT INTO contracts (
            contract_no, title, counterparty, amount, amount_minor, sign_date, owner,
            status, template_name, docx_path, values_json, expiry_date,
            project_name, coverage_start, coverage_end, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary.get('contract_no'),
            summary.get('title') or '未命名合同',
            summary.get('counterparty'),
            amount,
            amount_minor,
            summary.get('sign_date'),
            summary.get('owner'),
            status,
            summary.get('template_name'),
            stored_docx_path,
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
    for plan in plans or []:
        _insert_payment_plan_impl(conn, contract_id, plan)
    return contract_id, len(plans or [])


def create_contract_with_plans(summary, field_values, docx_path, plans, conn=None):
    """在单个事务中创建合同并批量插入付款计划，保证原子性。

    返回 (contract_id, plan_count)。
    """
    try:
        if conn is not None:
            return _create_contract_with_plans_impl(
                conn, summary, field_values, docx_path, plans
            )
        with get_conn() as managed_conn:
            return _create_contract_with_plans_impl(
                managed_conn, summary, field_values, docx_path, plans
            )
    except sqlite3.IntegrityError as e:
        if 'contract_no' in str(e).lower() or 'idx_contracts_contract_no_unique' in str(e).lower():
            raise ValueError('合同编号已存在') from e
        raise


def update_contract(contract_id, data):
    assignments = []
    values = []
    for key in CONTRACT_UPDATE_FIELDS:
        if key in data:
            if key == 'status':
                data[key] = _validate_choice(data[key], CONTRACT_STATUSES, '合同状态')
            if key == 'amount':
                amount_minor, amount = _amount_pair(data[key])
                data[key] = amount
                assignments.extend(['amount = ?', 'amount_minor = ?'])
                values.extend([amount, amount_minor])
                continue
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
                for key in CONTRACT_UPDATE_FIELDS:
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


def contract_no_exists(contract_no, exclude_id=None):
    """Return whether a non-empty contract number is already used."""
    contract_no = str(contract_no or '').strip()
    if not contract_no:
        return False
    sql = "SELECT 1 FROM contracts WHERE contract_no = ?"
    params = [contract_no]
    if exclude_id is not None:
        sql += ' AND id != ?'
        params.append(int(exclude_id))
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone() is not None


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


def iter_contracts(q='', status='', batch_size=500, include_deleted=False,
                   deleted_only=False):
    return list_queries.iter_contracts(
        get_conn, row_to_dict, q=q, status=status, batch_size=batch_size,
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
    return _PAYMENT_PLANS.insert(contract_id, plan)


def insert_payment_plans(contract_id, plans):
    """批量插入付款计划 —— 在单个事务内完成，保证原子性。"""
    return _PAYMENT_PLANS.insert_many(contract_id, plans)


def _insert_payment_plan_impl(conn, contract_id, plan):
    """在已有连接中插入单条付款计划（由 insert_payment_plans 调用）"""
    return _PAYMENT_PLANS.insert_impl(conn, contract_id, plan)


def _normalize_payment_consistency(plan):
    """校验金额/日期关系，并由金额统一推导付款状态。"""
    return _PAYMENT_PLANS.normalize_consistency(plan)


def _append_plan_assignment(assignments, values, key, row):
    _PAYMENT_PLANS.append_assignment(assignments, values, key, row)


def save_payment_plan_changes(contract_id, changes):
    """在一个事务中保存付款计划的新增、修改和删除。"""
    return _PAYMENT_PLANS.save_changes(contract_id, changes)


def list_payment_plans(contract_id=None, confirm_status='', payment_status='',
                       start_date='', end_date='', project_name='', page=0,
                       per_page=20, limit=0):
    return _PAYMENT_PLANS.list(
        contract_id=contract_id, confirm_status=confirm_status,
        payment_status=payment_status,
        start_date=start_date, end_date=end_date, project_name=project_name,
        page=page, per_page=per_page, limit=limit,
    )


def get_payment_plan(plan_id):
    """Return a payment plan with basic contract context."""
    return _PAYMENT_PLANS.get(plan_id)


def update_payment_plan(plan_id, data, contract_id=None):
    return _PAYMENT_PLANS.update(plan_id, data, contract_id=contract_id)


def batch_confirm_plans(plan_ids, contract_id=None):
    """在单个事务中批量确认付款计划，保证原子性。"""
    return _PAYMENT_PLANS.batch_confirm(plan_ids, contract_id=contract_id)


def batch_mark_plans_paid(plan_ids, paid_date):
    """Mark confirmed unpaid plans as fully paid in one transaction."""
    return _PAYMENT_PLANS.batch_mark_paid(plan_ids, paid_date)


def delete_payment_plan(plan_id, contract_id=None):
    return _PAYMENT_PLANS.delete(plan_id, contract_id=contract_id)


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


def get_expiring_contracts(days=30, limit=0):
    """获取 N 天内到期的合同（已签订/履行中，未软删除）"""
    return dashboard_queries.get_expiring_contracts(
        get_conn, row_to_dict, days, limit=limit
    )


def get_due_soon_payments(days=7, limit=0):
    """N 天内到期、已确认、未付清的付款计划"""
    return dashboard_queries.get_due_soon_payments(
        get_conn, row_to_dict, days, limit=limit
    )


def get_recent_contracts(limit=5):
    """最近 N 的合同（排除已软删除）"""
    return dashboard_queries.get_recent_contracts(get_conn, row_to_dict, limit)


# ── Soft delete / trash ──

_contract_lifecycle = ContractLifecycleRepository(
    get_conn, _now, _validate_choice, CONTRACT_STATUSES, row_to_dict,
)

def soft_delete_contract(contract_id):
    """软删除合同（设置 deleted_at 标记，不实际删除数据）"""
    return _contract_lifecycle.soft_delete(contract_id)


def restore_contract(contract_id):
    """从回收站恢复软删除的合同"""
    return _contract_lifecycle.restore(contract_id)


def permanently_delete_contract(contract_id):
    """永久删除合同及其关联数据（仅限已在回收站中的合同）"""
    return _contract_lifecycle.permanently_delete(contract_id)


def discard_unlinked_contract(contract_id):
    """清理本次生成但尚未建立采购关联的合同。"""
    return _contract_lifecycle.discard_unlinked(contract_id)


# ── Batch operations ──

def batch_delete_contracts(ids):
    """软删除多个合同（设置 deleted_at 标记，保留数据）"""
    return _contract_lifecycle.batch_delete(ids)


def batch_update_status(ids, status):
    """Batch update contract status."""
    return _contract_lifecycle.batch_update_status(ids, status)


# ── Contract history ──

def get_contract_history(contract_id):
    return _contract_lifecycle.history(contract_id)
