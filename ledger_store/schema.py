"""Schema SQL and migrations for the contract ledger database."""

LEDGER_SCHEMA_SQL = """
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

CREATE INDEX IF NOT EXISTS idx_contracts_status
    ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_expiry
    ON contracts(expiry_date);
"""


SCHEMA_VERSION_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
)
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
]
