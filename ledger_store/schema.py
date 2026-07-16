"""Schema SQL and migrations for the contract ledger database."""

LEDGER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT,
    title TEXT NOT NULL,
    counterparty TEXT,
    amount REAL,
    amount_minor INTEGER,
    sign_date TEXT,
    expiry_date TEXT DEFAULT '',
    owner TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','signed','active','completed','void')),
    template_name TEXT,
    docx_path TEXT,
    values_json TEXT,
    project_name TEXT DEFAULT '',
    coverage_start INTEGER,
    coverage_end INTEGER,
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
    due_amount_minor INTEGER,
    paid_amount REAL NOT NULL DEFAULT 0,
    paid_amount_minor INTEGER NOT NULL DEFAULT 0,
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

"""


LEDGER_INDEX_SQL = """
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

CREATE INDEX IF NOT EXISTS idx_contracts_status
    ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_expiry
    ON contracts(expiry_date);
"""


LEDGER_SCHEMA_SQL = LEDGER_TABLE_SQL + "\n" + LEDGER_INDEX_SQL


SCHEMA_VERSION_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


CURRENT_SCHEMA_VERSION = 16


# Indexes introduced by historical migrations but required immediately for a
# brand-new database that is stamped directly at CURRENT_SCHEMA_VERSION.
FRESH_DATABASE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_contracts_project
    ON contracts(project_name, coverage_end);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contracts_contract_no_unique
    ON contracts(contract_no)
    WHERE contract_no IS NOT NULL AND TRIM(contract_no) != '';
CREATE INDEX IF NOT EXISTS idx_payment_actionable_due
    ON payment_plans(due_date, contract_id)
    WHERE confirm_status = 'confirmed' AND payment_status != 'paid';
CREATE TABLE IF NOT EXISTS contract_generation_jobs (
    job_id TEXT PRIMARY KEY,
    state TEXT NOT NULL
        CHECK(state IN (
            'prepared','staged','file_moved','completed',
            'failed','recovered','attention'
        )),
    contract_id INTEGER,
    output_path TEXT NOT NULL,
    staging_path TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    recovery_action TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_state_updated
    ON contract_generation_jobs(state, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_generation_jobs_active_output
    ON contract_generation_jobs(output_path COLLATE NOCASE)
    WHERE state IN ('prepared', 'staged', 'file_moved');
"""


# 格式: (version, forward_sql, rollback_sql)
# rollback_sql 在迁移失败时执行，留空表示不可回滚
MIGRATIONS = [
    # v2: 软删除支持
    (
        2,
        "ALTER TABLE contracts ADD COLUMN deleted_at TEXT DEFAULT '';",
        "ALTER TABLE contracts DROP COLUMN deleted_at;",
    ),
    # v3: 合同到期日
    (
        3,
        "ALTER TABLE contracts ADD COLUMN expiry_date TEXT DEFAULT '';",
        "ALTER TABLE contracts DROP COLUMN expiry_date;",
    ),
    # v4-v6: 项目归类与合同覆盖号段
    (
        4,
        "ALTER TABLE contracts ADD COLUMN project_name TEXT DEFAULT '';",
        "ALTER TABLE contracts DROP COLUMN project_name;",
    ),
    (
        5,
        "ALTER TABLE contracts ADD COLUMN coverage_start INTEGER;",
        "ALTER TABLE contracts DROP COLUMN coverage_start;",
    ),
    (
        6,
        "ALTER TABLE contracts ADD COLUMN coverage_end INTEGER;",
        "ALTER TABLE contracts DROP COLUMN coverage_end;",
    ),
    (
        7,
        "CREATE INDEX IF NOT EXISTS idx_contracts_project ON contracts(project_name, coverage_end);",
        "DROP INDEX IF EXISTS idx_contracts_project;",
    ),
    # v8: 非空合同编号唯一
    (
        8,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contracts_contract_no_unique "
        "ON contracts(contract_no) WHERE contract_no IS NOT NULL AND TRIM(contract_no) != '';",
        "DROP INDEX IF EXISTS idx_contracts_contract_no_unique;",
    ),
    # v9-v11: 金额改用整数分作为权威存储，旧 REAL 列暂留作兼容镜像
    (
        9,
        "ALTER TABLE contracts ADD COLUMN amount_minor INTEGER;",
        "ALTER TABLE contracts DROP COLUMN amount_minor;",
    ),
    (
        10,
        "ALTER TABLE payment_plans ADD COLUMN due_amount_minor INTEGER;",
        "ALTER TABLE payment_plans DROP COLUMN due_amount_minor;",
    ),
    (
        11,
        "ALTER TABLE payment_plans ADD COLUMN paid_amount_minor INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE payment_plans DROP COLUMN paid_amount_minor;",
    ),
    # v12: 将运行目录内的合同绝对路径规范为可迁移的相对路径
    (
        12,
        "SELECT 1;",
        "",
    ),
    # v13: 首页和付款工作台的高频待付款日期查询
    (
        13,
        "CREATE INDEX IF NOT EXISTS idx_payment_actionable_due "
        "ON payment_plans(due_date, contract_id) "
        "WHERE confirm_status = 'confirmed' AND payment_status != 'paid';",
        "DROP INDEX IF EXISTS idx_payment_actionable_due;",
    ),
    # v14-v16: persistent generation journal and active output reservation.
    (
        14,
        "CREATE TABLE IF NOT EXISTS contract_generation_jobs ("
        "job_id TEXT PRIMARY KEY, "
        "state TEXT NOT NULL CHECK(state IN ("
        "'prepared','staged','file_moved','completed','failed','recovered','attention')), "
        "contract_id INTEGER, output_path TEXT NOT NULL, staging_path TEXT NOT NULL, "
        "error TEXT NOT NULL DEFAULT '', recovery_action TEXT NOT NULL DEFAULT '', "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT NOT NULL DEFAULT ''"
        ");",
        "DROP TABLE IF EXISTS contract_generation_jobs;",
    ),
    (
        15,
        "CREATE INDEX IF NOT EXISTS idx_generation_jobs_state_updated "
        "ON contract_generation_jobs(state, updated_at DESC);",
        "DROP INDEX IF EXISTS idx_generation_jobs_state_updated;",
    ),
    (
        16,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_generation_jobs_active_output "
        "ON contract_generation_jobs(output_path COLLATE NOCASE) "
        "WHERE state IN ('prepared', 'staged', 'file_moved');",
        "DROP INDEX IF EXISTS idx_generation_jobs_active_output;",
    ),
]


# Data backfills are named separately from DDL so migration execution remains
# declarative and future versions do not extend a version-specific if/elif chain.
MIGRATION_BACKFILLS = {
    9: """UPDATE contracts
          SET amount_minor = CAST(ROUND(amount * 100) AS INTEGER)
          WHERE amount IS NOT NULL AND amount_minor IS NULL""",
    10: """UPDATE payment_plans
           SET due_amount_minor = CAST(ROUND(due_amount * 100) AS INTEGER)
           WHERE due_amount IS NOT NULL AND due_amount_minor IS NULL""",
    11: """UPDATE payment_plans
           SET paid_amount_minor = CAST(ROUND(COALESCE(paid_amount, 0) * 100) AS INTEGER)
           WHERE paid_amount_minor IS NULL OR paid_amount_minor = 0""",
}

DOCUMENT_PATH_MIGRATION_VERSION = 12
