"""Local storage for contract ledger and payment plans."""

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from utils.logger import get_logger
from utils.security import path_within as _path_within
from utils.constants import (
    ContractStatus, PaymentStatus, ConfirmStatus, ConfidenceLevel,
)

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
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_no TEXT,
                title TEXT NOT NULL,
                counterparty TEXT,
                amount REAL,
                sign_date TEXT,
                expiry_date TEXT DEFAULT '',
                owner TEXT,
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK(status IN ('draft','signed','active','completed','void')),
                template_name TEXT,
                docx_path TEXT,
                values_json TEXT,
                deleted_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payment_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                phase_name TEXT,
                payment_type TEXT NOT NULL DEFAULT 'conditional'
                    CHECK(payment_type IN ('conditional','fixed_date')),
                trigger_event TEXT,
                trigger_days INTEGER,
                expected_trigger_date TEXT,
                due_date TEXT,
                ratio REAL,
                due_amount REAL,
                paid_amount REAL NOT NULL DEFAULT 0,
                paid_date TEXT,
                condition_text TEXT,
                source_text TEXT,
                confidence TEXT NOT NULL DEFAULT 'low'
                    CHECK(confidence IN ('low','medium','high')),
                confirm_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(confirm_status IN ('pending','confirmed','void')),
                payment_status TEXT NOT NULL DEFAULT 'unpaid'
                    CHECK(payment_status IN ('unpaid','partial','paid')),
                remark TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contract_id) REFERENCES contracts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_contracts_created
                ON contracts(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_payment_contract
                ON payment_plans(contract_id);
            CREATE INDEX IF NOT EXISTS idx_payment_due
                ON payment_plans(confirm_status, payment_status, due_date);

            CREATE TABLE IF NOT EXISTS contract_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_at TEXT NOT NULL,
                FOREIGN KEY(contract_id) REFERENCES contracts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_history_contract
                ON contract_history(contract_id, changed_at DESC);
            """
        )
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
    # 确保迁移在 init 后立即执行
    run_migrations()


# ── Migrations ──
# 格式: (version, forward_sql, rollback_sql)
# rollback_sql 在迁移失败时执行，留空表示不可回滚

MIGRATIONS = [
    # v2: 软删除支持
    (2,
     "ALTER TABLE contracts ADD COLUMN deleted_at TEXT DEFAULT '';",
     "ALTER TABLE contracts DROP COLUMN deleted_at;"),
    # v3: 合同到期日
    (3,
     "ALTER TABLE contracts ADD COLUMN expiry_date TEXT DEFAULT '';",
     "ALTER TABLE contracts DROP COLUMN expiry_date;"),
]


def run_migrations():
    with get_conn() as conn:
        cur = conn.execute('SELECT MAX(version) FROM schema_version')
        row = cur.fetchone()
        current = row[0] if row and row[0] is not None else 0
        for version, forward_sql, rollback_sql in MIGRATIONS:
            if version <= current:
                continue
            try:
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
    try:
        src_conn = sqlite3.connect(src)
        row = src_conn.execute('PRAGMA quick_check').fetchone()
        src_conn.close()
        if row is None or row[0] != 'ok':
            raise ValueError(f'备份文件校验失败: {row[0] if row else "无法读取"}')
    except sqlite3.DatabaseError as e:
        raise ValueError(f'备份文件不是有效的 SQLite 数据库: {e}')
    if os.path.exists(DB_PATH):
        create_backup('before_restore')
    os.makedirs(DATA_DIR, exist_ok=True)
    shutil.copy2(src, DB_PATH)
    return DB_PATH


def row_to_dict(row):
    return dict(row) if row is not None else None


def create_contract(summary, field_values, docx_path):
    now = _now()
    status = _validate_choice(summary.get('status') or 'draft', CONTRACT_STATUSES, '合同状态')
    values_json = json.dumps(field_values or {}, ensure_ascii=False, default=str)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO contracts (
                contract_no, title, counterparty, amount, sign_date, owner,
                status, template_name, docx_path, values_json, expiry_date,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now,
                now,
            ),
        )
        return cur.lastrowid


def create_contract_with_plans(summary, field_values, docx_path, plans):
    """在单个事务中创建合同并批量插入付款计划，保证原子性。

    返回 (contract_id, plan_count)。
    """
    now = _now()
    status = _validate_choice(summary.get('status') or 'draft', CONTRACT_STATUSES, '合同状态')
    values_json = json.dumps(field_values or {}, ensure_ascii=False, default=str)
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO contracts (
                contract_no, title, counterparty, amount, sign_date, owner,
                status, template_name, docx_path, values_json, expiry_date,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def update_contract(contract_id, data):
    allowed = ['contract_no', 'title', 'counterparty', 'amount', 'sign_date', 'expiry_date', 'owner', 'status']
    old_contract = get_contract(contract_id)
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
    with get_conn() as conn:
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


def get_contract(contract_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM contracts WHERE id = ?', (contract_id,)).fetchone()
    return row_to_dict(row)


def list_contracts(q='', status='', page=1, per_page=20, include_deleted=False):
    """列出合同台账，支持关键词搜索和状态筛选。

    使用 EXISTS 子查询替代 LEFT JOIN 以避免支付计划行膨胀。
    默认排除已软删除的合同。
    """
    base_sql = "FROM contracts c"
    clauses = []
    params = []
    if not include_deleted:
        clauses.append("(c.deleted_at = '' OR c.deleted_at IS NULL)")
    if q:
        like = f'%{q}%'
        clauses.append(
            '(c.contract_no LIKE ? OR c.title LIKE ? OR c.counterparty LIKE ? '
            'OR c.owner LIKE ? OR c.values_json LIKE ? '
            'OR EXISTS (SELECT 1 FROM payment_plans p WHERE p.contract_id = c.id '
            'AND (p.condition_text LIKE ? OR p.source_text LIKE ? OR p.phase_name LIKE ?)))'
        )
        params.extend([like] * 8)
    if status:
        clauses.append('c.status = ?')
        params.append(status)
    where = ''
    if clauses:
        where = ' WHERE ' + ' AND '.join(clauses)

    count_sql = f'SELECT COUNT(*) {base_sql}{where}'
    with get_conn() as conn:
        total = conn.execute(count_sql, params).fetchone()[0]

    offset = max(0, (page - 1) * per_page)
    sql = f"""
        SELECT c.*,
               (SELECT COUNT(*) FROM payment_plans p WHERE p.contract_id = c.id) AS plan_count,
               (SELECT COUNT(*) FROM payment_plans p WHERE p.contract_id = c.id
                  AND p.confirm_status = 'pending') AS pending_count,
               (SELECT COUNT(*) FROM payment_plans p WHERE p.contract_id = c.id
                  AND p.confirm_status = 'confirmed' AND p.payment_status != 'paid') AS payable_count
        {base_sql}{where}
        ORDER BY c.created_at DESC
        LIMIT ? OFFSET ?
    """
    with get_conn() as conn:
        rows = conn.execute(sql, [*params, per_page, offset]).fetchall()
    return {
        'rows': [row_to_dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page or 1,
    }


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


def list_payment_plans(contract_id=None, confirm_status='', payment_status='',
                       start_date='', end_date='', page=0, per_page=20):
    base_sql = """
        FROM payment_plans p
        JOIN contracts c ON c.id = p.contract_id
    """
    clauses = ["(c.deleted_at = '' OR c.deleted_at IS NULL)"]
    params = []
    if contract_id:
        clauses.append('p.contract_id = ?')
        params.append(contract_id)
    if confirm_status:
        clauses.append('p.confirm_status = ?')
        params.append(confirm_status)
    if payment_status:
        clauses.append('p.payment_status = ?')
        params.append(payment_status)
    if start_date:
        clauses.append('p.due_date >= ?')
        params.append(start_date)
    if end_date:
        clauses.append('p.due_date <= ?')
        params.append(end_date)
    where = ''
    if clauses:
        where = ' WHERE ' + ' AND '.join(clauses)

    if page > 0:
        count_sql = f'SELECT COUNT(*) {base_sql}{where}'
        with get_conn() as conn:
            total = conn.execute(count_sql, params).fetchone()[0]
        offset = max(0, (page - 1) * per_page)
        sql = f"""
            SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
                   c.amount AS contract_amount
            {base_sql}{where}
            ORDER BY COALESCE(p.due_date, '9999-12-31'), p.id
            LIMIT ? OFFSET ?
        """
        with get_conn() as conn:
            rows = conn.execute(sql, [*params, per_page, offset]).fetchall()
        return {
            'rows': [row_to_dict(r) for r in rows],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page or 1,
        }

    sql = f"""
        SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
               c.amount AS contract_amount
        {base_sql}{where}
        ORDER BY COALESCE(p.due_date, '9999-12-31'), p.id
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]


def update_payment_plan(plan_id, data, contract_id=None):
    allowed = [
        'phase_name', 'payment_type', 'trigger_event', 'trigger_days',
        'expected_trigger_date', 'due_date', 'ratio', 'due_amount',
        'paid_amount', 'paid_date', 'condition_text', 'source_text',
        'confidence', 'confirm_status', 'payment_status', 'remark',
    ]
    assignments = []
    values = []
    validators = {
        'payment_type': (PAYMENT_TYPES, '付款类型'),
        'confidence': (CONFIDENCE_LEVELS, '置信度'),
        'confirm_status': (CONFIRM_STATUSES, '确认状态'),
        'payment_status': (PAYMENT_STATUSES, '付款状态'),
    }
    for key in allowed:
        if key in data:
            if key in validators:
                allowed_values, label = validators[key]
                data[key] = _validate_choice(data[key], allowed_values, label)
            assignments.append(f'{key} = ?')
            values.append(data[key])
    if not assignments:
        return
    assignments.append('updated_at = ?')
    values.append(_now())
    values.append(plan_id)
    where = 'id = ?'
    if contract_id is not None:
        where += ' AND contract_id = ?'
        values.append(contract_id)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE payment_plans SET {', '.join(assignments)} WHERE {where}",
            values,
        )
        return cur.rowcount


def delete_payment_plan(plan_id, contract_id=None):
    sql = 'DELETE FROM payment_plans WHERE id = ?'
    params = [plan_id]
    if contract_id is not None:
        sql += ' AND contract_id = ?'
        params.append(contract_id)
    with get_conn() as conn:
        conn.execute(sql, params)


def next_month_payment_plans(start_date, end_date):
    sql = """
        SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty, c.owner,
               c.amount AS contract_amount
        FROM payment_plans p
        JOIN contracts c ON c.id = p.contract_id
        WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
          AND p.confirm_status = 'confirmed'
          AND p.payment_status != 'paid'
          AND p.due_date >= ?
          AND p.due_date <= ?
        ORDER BY p.due_date, c.counterparty, c.contract_no, p.id
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (start_date, end_date)).fetchall()
    return [row_to_dict(r) for r in rows]


def get_contract_stats():
    """合约统计：总数、各状态数、金额合计（排除已软删除的合同）"""
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL"
        ).fetchone()[0]
        status_rows = conn.execute(
            "SELECT status, COUNT(*), COALESCE(SUM(amount),0) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL GROUP BY status"
        ).fetchall()
        total_amount = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL"
        ).fetchone()[0]
    by_status = {row[0]: {'count': row[1], 'amount': row[2]} for row in status_rows}
    return {
        'total': total,
        'by_status': by_status,
        'total_amount': total_amount or 0,
    }


def get_payment_stats():
    """付款统计：应付/已付/未付金额（排除已软删除的合同）"""
    with get_conn() as conn:
        due = conn.execute(
            """SELECT COALESCE(SUM(p.due_amount),0) FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'confirmed' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
        paid = conn.execute(
            """SELECT COALESCE(SUM(p.paid_amount),0) FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'confirmed' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
        pending = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(p.due_amount),0)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'pending' AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()
        pending_missing_date = conn.execute(
            """SELECT COUNT(*)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE p.confirm_status = 'pending'
                 AND COALESCE(p.due_date, '') = ''
                 AND (c.deleted_at = '' OR c.deleted_at IS NULL)"""
        ).fetchone()[0]
    return {
        'total_due': due or 0,
        'total_paid': paid or 0,
        'total_unpaid': ((due or 0) - (paid or 0)),
        'pending_count': pending[0] or 0,
        'pending_amount': pending[1] or 0,
        'pending_missing_date': pending_missing_date or 0,
    }


def get_monthly_payments(year, month):
    """指定月份应付款统计：笔数和金额（排除已软删除的合同）"""
    ym = f'{year}-{month:02d}'
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(p.due_amount - COALESCE(p.paid_amount,0)),0)
               FROM payment_plans p
               JOIN contracts c ON c.id = p.contract_id
               WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
                 AND p.confirm_status = 'confirmed'
                 AND p.payment_status != 'paid'
                 AND p.due_date LIKE ?""",
            (ym + '%',)
        ).fetchone()
    return {'count': row[0], 'amount': row[1] or 0}


def get_expiring_contracts(days=30):
    """获取 N 天内到期的合同（已签订/履行中，未软删除）"""
    today = date.today()
    end = today + timedelta(days=days)
    sql = """
        SELECT * FROM contracts
        WHERE expiry_date != '' AND expiry_date IS NOT NULL
          AND status IN ('signed', 'active')
          AND (deleted_at = '' OR deleted_at IS NULL)
          AND expiry_date >= ? AND expiry_date <= ?
        ORDER BY expiry_date
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (
            today.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))).fetchall()
    return [row_to_dict(r) for r in rows]


def get_due_soon_payments(days=7):
    """N 天内到期、已确认、未付清的付款计划"""
    today = date.today()
    end = today + timedelta(days=days)
    sql = """
        SELECT p.*, c.contract_no, c.title AS contract_title,
               c.counterparty, c.owner
        FROM payment_plans p
        JOIN contracts c ON c.id = p.contract_id
        WHERE (c.deleted_at = '' OR c.deleted_at IS NULL)
          AND p.confirm_status = 'confirmed'
          AND p.payment_status != 'paid'
          AND p.due_date >= ? AND p.due_date <= ?
        ORDER BY p.due_date
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (
            today.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))).fetchall()
    return [row_to_dict(r) for r in rows]


def get_recent_contracts(limit=5):
    """最近 N 的合同（排除已软删除）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contracts WHERE deleted_at = '' OR deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


# ── Soft delete / trash ──

def soft_delete_contract(contract_id):
    """软删除合同（设置 deleted_at 标记，不实际删除数据）"""
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE contracts SET deleted_at = ?, updated_at = ? WHERE id = ? AND (deleted_at = '' OR deleted_at IS NULL)",
            (now, now, contract_id),
        )
        return cur.rowcount


def restore_contract(contract_id):
    """从回收站恢复软删除的合同"""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE contracts SET deleted_at = '', updated_at = ? WHERE id = ? AND deleted_at != '' AND deleted_at IS NOT NULL",
            (_now(), contract_id),
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
        cur = conn.execute(
            f"UPDATE contracts SET status = ?, updated_at = ? WHERE id IN ({placeholders})",
            [status, now] + ids,
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
