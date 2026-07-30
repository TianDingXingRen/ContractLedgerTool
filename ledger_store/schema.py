"""Schema SQL and migrations for the contract ledger database."""

from . import invoice_constraints

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
    record_origin TEXT NOT NULL DEFAULT 'generated'
        CHECK(record_origin IN ('generated','imported')),
    original_filename TEXT DEFAULT '',
    source_sha256 TEXT DEFAULT '',
    project_name TEXT DEFAULT '',
    coverage_start INTEGER,
    coverage_end INTEGER,
    deleted_at TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_serials (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, serial_no INTEGER NOT NULL CHECK(serial_no > 0), amount_minor INTEGER CHECK(amount_minor IS NULL OR amount_minor >= 0), status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')), remark TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(contract_id, serial_no), FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);

CREATE TABLE IF NOT EXISTS payment_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    group_key TEXT NOT NULL DEFAULT '',
    phase_name TEXT,
    rule_type TEXT NOT NULL DEFAULT 'conditional'
        CHECK(rule_type IN ('conditional','recurring')),
    scope TEXT NOT NULL DEFAULT 'contract'
        CHECK(scope IN ('contract','production_notice','delivery_batch','settlement_period','other')),
    trigger_event_type TEXT NOT NULL DEFAULT 'other',
    trigger_event TEXT,
    trigger_days INTEGER,
    due_date TEXT,
    conditions_json TEXT NOT NULL DEFAULT '[]',
    condition_logic TEXT NOT NULL DEFAULT 'SINGLE'
        CHECK(condition_logic IN ('SINGLE','AND','OR','OTHER')),
    amount_basis TEXT NOT NULL DEFAULT 'unknown',
    amount_basis_text TEXT NOT NULL DEFAULT '',
    ratio REAL,
    explicit_amount_minor INTEGER,
    calculated_amount_minor INTEGER,
    repeat_mode TEXT NOT NULL DEFAULT 'once'
        CHECK(repeat_mode IN ('once','each_event')),
    source_text TEXT,
    source_block TEXT NOT NULL DEFAULT '',
    rule_fingerprint TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL DEFAULT '',
    extractor_version TEXT NOT NULL DEFAULT '',
    rule_version INTEGER NOT NULL DEFAULT 1,
    parse_status TEXT NOT NULL DEFAULT 'manual'
        CHECK(parse_status IN ('exact','partial','conflict','unsupported','manual')),
    reason_codes_json TEXT NOT NULL DEFAULT '[]',
    confirm_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(confirm_status IN ('pending','confirmed','void')),
    user_modified INTEGER NOT NULL DEFAULT 0 CHECK(user_modified IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(contract_id) REFERENCES contracts(id)
);

CREATE TABLE IF NOT EXISTS payment_trigger_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    reference_no TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL DEFAULT '',
    base_amount_minor INTEGER,
    reference_name TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(contract_id) REFERENCES contracts(id)
);

CREATE TABLE IF NOT EXISTS payment_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    contract_serial_id INTEGER,
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
    payment_rule_id INTEGER,
    trigger_event_id INTEGER,
    instance_key TEXT NOT NULL DEFAULT '',
    calculation_base_minor INTEGER,
    amount_basis TEXT NOT NULL DEFAULT '',
    explicit_amount_minor INTEGER,
    calculated_amount_minor INTEGER,
    parse_status TEXT NOT NULL DEFAULT 'manual'
        CHECK(parse_status IN ('exact','partial','conflict','unsupported','manual')),
    reason_codes_json TEXT NOT NULL DEFAULT '[]',
    extractor_version TEXT NOT NULL DEFAULT '',
    user_modified INTEGER NOT NULL DEFAULT 0 CHECK(user_modified IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(contract_id) REFERENCES contracts(id),
    FOREIGN KEY(contract_serial_id) REFERENCES contract_serials(id),
    FOREIGN KEY(payment_rule_id) REFERENCES payment_rules(id),
    FOREIGN KEY(trigger_event_id) REFERENCES payment_trigger_events(id)
);

CREATE TABLE IF NOT EXISTS contract_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual'
        CHECK(source_type IN ('manual','procurement_award','contract_import')),
    source_id INTEGER,
    line_no INTEGER NOT NULL,
    item_code TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL,
    spec_model TEXT NOT NULL DEFAULT '',
    drawing_no TEXT NOT NULL DEFAULT '',
    quantity_text TEXT NOT NULL DEFAULT '',
    contracted_qty INTEGER NOT NULL CHECK(contracted_qty > 0),
    unit TEXT NOT NULL DEFAULT '个',
    unit_price_minor INTEGER CHECK(unit_price_minor IS NULL OR unit_price_minor >= 0),
    amount_minor INTEGER CHECK(amount_minor IS NULL OR amount_minor >= 0),
    serial_start INTEGER,
    serial_end INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(contract_id, line_no),
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contract_item_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    item_id INTEGER,
    action TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '',
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS production_notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    notice_no TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    notice_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','issued','acknowledged','closed','cancelled')),
    supplier_name TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    supersedes_notice_id INTEGER,
    total_qty INTEGER NOT NULL DEFAULT 0 CHECK(total_qty >= 0),
    total_amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(total_amount_minor >= 0),
    issued_at TEXT NOT NULL DEFAULT '',
    issued_by TEXT NOT NULL DEFAULT '',
    acknowledged_at TEXT NOT NULL DEFAULT '',
    acknowledged_by TEXT NOT NULL DEFAULT '',
    closed_at TEXT NOT NULL DEFAULT '',
    cancelled_at TEXT NOT NULL DEFAULT '',
    cancelled_by TEXT NOT NULL DEFAULT '',
    cancellation_reason TEXT NOT NULL DEFAULT '',
    payment_trigger_event_id INTEGER,
    remark TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(contract_id, notice_no, version),
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT,
    FOREIGN KEY(supersedes_notice_id) REFERENCES production_notices(id),
    FOREIGN KEY(payment_trigger_event_id) REFERENCES payment_trigger_events(id)
);

CREATE TABLE IF NOT EXISTS production_notice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id INTEGER NOT NULL,
    contract_item_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    spec_model TEXT NOT NULL DEFAULT '',
    drawing_no TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '个',
    notice_qty INTEGER NOT NULL CHECK(notice_qty > 0),
    unit_price_minor INTEGER CHECK(unit_price_minor IS NULL OR unit_price_minor >= 0),
    amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(amount_minor >= 0),
    serial_start INTEGER,
    serial_end INTEGER,
    required_delivery_date TEXT NOT NULL DEFAULT '',
    remark TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(notice_id, line_no),
    UNIQUE(notice_id, contract_item_id),
    FOREIGN KEY(notice_id) REFERENCES production_notices(id) ON DELETE CASCADE,
    FOREIGN KEY(contract_item_id) REFERENCES contract_items(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS production_notice_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT NOT NULL DEFAULT '',
    to_status TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(notice_id) REFERENCES production_notices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_code TEXT NOT NULL DEFAULT '',
    invoice_no TEXT NOT NULL,
    invoice_type TEXT NOT NULL DEFAULT 'vat_special',
    issue_date TEXT NOT NULL DEFAULT '',
    received_date TEXT NOT NULL DEFAULT '',
    seller_name TEXT NOT NULL DEFAULT '',
    seller_tax_no TEXT NOT NULL DEFAULT '',
    buyer_name TEXT NOT NULL DEFAULT '',
    buyer_tax_no TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CNY',
    amount_ex_tax_minor INTEGER NOT NULL DEFAULT 0 CHECK(amount_ex_tax_minor >= 0),
    tax_amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(tax_amount_minor >= 0),
    total_amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(total_amount_minor >= 0),
    tax_rate_bps INTEGER CHECK(tax_rate_bps IS NULL OR tax_rate_bps >= 0),
    invoice_status TEXT NOT NULL DEFAULT 'valid'
        CHECK(invoice_status IN ('valid','red','void')),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(review_status IN ('pending','verified','exception')),
    deduction_status TEXT NOT NULL DEFAULT 'not_applicable'
        CHECK(deduction_status IN ('not_applicable','pending','deducted')),
    original_invoice_id INTEGER,
    remark TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(original_invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS invoice_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    contract_id INTEGER NOT NULL,
    production_notice_id INTEGER,
    payment_plan_id INTEGER,
    allocated_amount_minor INTEGER NOT NULL CHECK(allocated_amount_minor > 0),
    remark TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT,
    FOREIGN KEY(production_notice_id) REFERENCES production_notices(id) ON DELETE RESTRICT,
    FOREIGN KEY(payment_plan_id) REFERENCES payment_plans(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS invoice_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    file_size INTEGER NOT NULL DEFAULT 0 CHECK(file_size >= 0),
    sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoice_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
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


CURRENT_SCHEMA_VERSION = 67


# Indexes introduced by historical migrations but required immediately for a
# brand-new database that is stamped directly at CURRENT_SCHEMA_VERSION.
FRESH_DATABASE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_contracts_project ON contracts(project_name, coverage_end);
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_contracts_import_sha256_unique
    ON contracts(source_sha256)
    WHERE record_origin = 'imported' AND source_sha256 != '';
CREATE INDEX IF NOT EXISTS idx_payment_rules_contract
    ON payment_rules(contract_id, confirm_status, parse_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_rules_fingerprint
    ON payment_rules(contract_id, rule_fingerprint);
CREATE INDEX IF NOT EXISTS idx_payment_events_contract
    ON payment_trigger_events(contract_id, event_type, event_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_events_reference
    ON payment_trigger_events(contract_id, event_type, reference_no)
    WHERE reference_no != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_instance_key
    ON payment_plans(instance_key) WHERE instance_key != '';
CREATE INDEX IF NOT EXISTS idx_contract_items_contract
    ON contract_items(contract_id, line_no);
CREATE INDEX IF NOT EXISTS idx_contract_serials_contract ON contract_serials(contract_id, status, serial_no);
CREATE INDEX IF NOT EXISTS idx_payment_serial ON payment_plans(contract_serial_id, due_date) WHERE contract_serial_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contract_item_history_contract
    ON contract_item_history(contract_id, created_at DESC, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contract_items_source
    ON contract_items(contract_id, source_type, source_id)
    WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_production_notices_contract
    ON production_notices(contract_id, status, notice_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_production_notice_items_contract_item
    ON production_notice_items(contract_item_id, notice_id);
CREATE INDEX IF NOT EXISTS idx_production_history_notice
    ON production_notice_history(notice_id, created_at DESC, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_business_unique
    ON invoices(seller_tax_no, invoice_code, invoice_no)
    WHERE invoice_no != '';
CREATE INDEX IF NOT EXISTS idx_invoices_status_date
    ON invoices(review_status, invoice_status, issue_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_invoice_allocations_contract
    ON invoice_allocations(contract_id, invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_allocations_notice
    ON invoice_allocations(production_notice_id) WHERE production_notice_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_invoice_allocations_payment
    ON invoice_allocations(payment_plan_id) WHERE payment_plan_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_files_hash
    ON invoice_files(invoice_id, sha256) WHERE sha256 != '';
CREATE INDEX IF NOT EXISTS idx_invoice_history_invoice ON invoice_history(invoice_id, created_at DESC, id DESC);
""" + invoice_constraints.INVOICE_RED_CONSISTENCY_SQL + """
CREATE TRIGGER IF NOT EXISTS trg_production_notice_single_active_insert
BEFORE INSERT ON production_notices
WHEN NEW.status IN ('issued','acknowledged','closed')
 AND EXISTS (
     SELECT 1 FROM production_notices existing
     WHERE existing.contract_id = NEW.contract_id
       AND existing.notice_no = NEW.notice_no
       AND existing.status IN ('issued','acknowledged','closed')
 )
BEGIN
    SELECT RAISE(ABORT, '同一投产通知只能有一个生效版本');
END;
CREATE TRIGGER IF NOT EXISTS trg_production_notice_single_active_update
BEFORE UPDATE OF status, notice_no, contract_id ON production_notices
WHEN NEW.status IN ('issued','acknowledged','closed')
 AND EXISTS (
     SELECT 1 FROM production_notices existing
     WHERE existing.contract_id = NEW.contract_id
       AND existing.notice_no = NEW.notice_no
       AND existing.id != NEW.id
       AND existing.status IN ('issued','acknowledged','closed')
 )
BEGIN
    SELECT RAISE(ABORT, '同一投产通知只能有一个生效版本');
END;
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
    (
        17,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contracts_import_sha256_unique "
        "ON contracts(source_sha256) "
        "WHERE record_origin = 'imported' AND source_sha256 != '';",
        "DROP INDEX IF EXISTS idx_contracts_import_sha256_unique;",
    ),
    (
        18,
        "CREATE TABLE IF NOT EXISTS payment_rules ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, "
        "group_key TEXT NOT NULL DEFAULT '', phase_name TEXT, "
        "rule_type TEXT NOT NULL DEFAULT 'conditional' CHECK(rule_type IN ('conditional','recurring')), "
        "scope TEXT NOT NULL DEFAULT 'contract' CHECK(scope IN ('contract','production_notice','delivery_batch','settlement_period','other')), "
        "trigger_event_type TEXT NOT NULL DEFAULT 'other', trigger_event TEXT, trigger_days INTEGER, due_date TEXT, "
        "conditions_json TEXT NOT NULL DEFAULT '[]', condition_logic TEXT NOT NULL DEFAULT 'SINGLE' CHECK(condition_logic IN ('SINGLE','AND','OR','OTHER')), "
        "amount_basis TEXT NOT NULL DEFAULT 'unknown', amount_basis_text TEXT NOT NULL DEFAULT '', ratio REAL, "
        "explicit_amount_minor INTEGER, calculated_amount_minor INTEGER, "
        "repeat_mode TEXT NOT NULL DEFAULT 'once' CHECK(repeat_mode IN ('once','each_event')), "
        "source_text TEXT, source_block TEXT NOT NULL DEFAULT '', rule_fingerprint TEXT NOT NULL, "
        "source_fingerprint TEXT NOT NULL DEFAULT '', extractor_version TEXT NOT NULL DEFAULT '', "
        "rule_version INTEGER NOT NULL DEFAULT 1, parse_status TEXT NOT NULL DEFAULT 'manual' "
        "CHECK(parse_status IN ('exact','partial','conflict','unsupported','manual')), "
        "reason_codes_json TEXT NOT NULL DEFAULT '[]', confirm_status TEXT NOT NULL DEFAULT 'pending' "
        "CHECK(confirm_status IN ('pending','confirmed','void')), user_modified INTEGER NOT NULL DEFAULT 0 "
        "CHECK(user_modified IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "FOREIGN KEY(contract_id) REFERENCES contracts(id));",
        "DROP TABLE IF EXISTS payment_rules;",
    ),
    (19, "CREATE INDEX IF NOT EXISTS idx_payment_rules_contract ON payment_rules(contract_id, confirm_status, parse_status);", "DROP INDEX IF EXISTS idx_payment_rules_contract;"),
    (20, "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_rules_fingerprint ON payment_rules(contract_id, rule_fingerprint);", "DROP INDEX IF EXISTS idx_payment_rules_fingerprint;"),
    (
        21,
        "CREATE TABLE IF NOT EXISTS payment_trigger_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, event_type TEXT NOT NULL, "
        "reference_no TEXT NOT NULL DEFAULT '', event_date TEXT NOT NULL DEFAULT '', base_amount_minor INTEGER, "
        "reference_name TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}', "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(contract_id) REFERENCES contracts(id));",
        "DROP TABLE IF EXISTS payment_trigger_events;",
    ),
    (22, "CREATE INDEX IF NOT EXISTS idx_payment_events_contract ON payment_trigger_events(contract_id, event_type, event_date);", "DROP INDEX IF EXISTS idx_payment_events_contract;"),
    (23, "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_events_reference ON payment_trigger_events(contract_id, event_type, reference_no) WHERE reference_no != '';", "DROP INDEX IF EXISTS idx_payment_events_reference;"),
    (24, "ALTER TABLE payment_plans ADD COLUMN payment_rule_id INTEGER REFERENCES payment_rules(id);", "ALTER TABLE payment_plans DROP COLUMN payment_rule_id;"),
    (25, "ALTER TABLE payment_plans ADD COLUMN trigger_event_id INTEGER REFERENCES payment_trigger_events(id);", "ALTER TABLE payment_plans DROP COLUMN trigger_event_id;"),
    (26, "ALTER TABLE payment_plans ADD COLUMN instance_key TEXT NOT NULL DEFAULT '';", "ALTER TABLE payment_plans DROP COLUMN instance_key;"),
    (27, "ALTER TABLE payment_plans ADD COLUMN calculation_base_minor INTEGER;", "ALTER TABLE payment_plans DROP COLUMN calculation_base_minor;"),
    (28, "ALTER TABLE payment_plans ADD COLUMN amount_basis TEXT NOT NULL DEFAULT '';", "ALTER TABLE payment_plans DROP COLUMN amount_basis;"),
    (29, "ALTER TABLE payment_plans ADD COLUMN explicit_amount_minor INTEGER;", "ALTER TABLE payment_plans DROP COLUMN explicit_amount_minor;"),
    (30, "ALTER TABLE payment_plans ADD COLUMN calculated_amount_minor INTEGER;", "ALTER TABLE payment_plans DROP COLUMN calculated_amount_minor;"),
    (31, "ALTER TABLE payment_plans ADD COLUMN parse_status TEXT NOT NULL DEFAULT 'manual' CHECK(parse_status IN ('exact','partial','conflict','unsupported','manual'));", "ALTER TABLE payment_plans DROP COLUMN parse_status;"),
    (32, "ALTER TABLE payment_plans ADD COLUMN reason_codes_json TEXT NOT NULL DEFAULT '[]';", "ALTER TABLE payment_plans DROP COLUMN reason_codes_json;"),
    (33, "ALTER TABLE payment_plans ADD COLUMN extractor_version TEXT NOT NULL DEFAULT '';", "ALTER TABLE payment_plans DROP COLUMN extractor_version;"),
    (34, "ALTER TABLE payment_plans ADD COLUMN user_modified INTEGER NOT NULL DEFAULT 0 CHECK(user_modified IN (0,1));", "ALTER TABLE payment_plans DROP COLUMN user_modified;"),
    (35, "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_instance_key ON payment_plans(instance_key) WHERE instance_key != '';", "DROP INDEX IF EXISTS idx_payment_instance_key;"),
    (
        36,
        "CREATE TABLE IF NOT EXISTS contract_items (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, source_type TEXT NOT NULL DEFAULT 'manual' CHECK(source_type IN ('manual','procurement_award','contract_import')), source_id INTEGER, line_no INTEGER NOT NULL, item_code TEXT NOT NULL DEFAULT '', item_name TEXT NOT NULL, spec_model TEXT NOT NULL DEFAULT '', drawing_no TEXT NOT NULL DEFAULT '', quantity_text TEXT NOT NULL DEFAULT '', contracted_qty INTEGER NOT NULL CHECK(contracted_qty > 0), unit TEXT NOT NULL DEFAULT '个', unit_price_minor INTEGER CHECK(unit_price_minor IS NULL OR unit_price_minor >= 0), amount_minor INTEGER CHECK(amount_minor IS NULL OR amount_minor >= 0), serial_start INTEGER, serial_end INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(contract_id, line_no), FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);",
        "DROP TABLE IF EXISTS contract_items;",
    ),
    (37, "CREATE INDEX IF NOT EXISTS idx_contract_items_contract ON contract_items(contract_id, line_no);", "DROP INDEX IF EXISTS idx_contract_items_contract;"),
    (38, "CREATE UNIQUE INDEX IF NOT EXISTS idx_contract_items_source ON contract_items(contract_id, source_type, source_id) WHERE source_id IS NOT NULL;", "DROP INDEX IF EXISTS idx_contract_items_source;"),
    (
        39,
        "CREATE TABLE IF NOT EXISTS production_notices (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, notice_no TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0), notice_date TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','issued','acknowledged','closed','cancelled')), supplier_name TEXT NOT NULL DEFAULT '', project_name TEXT NOT NULL DEFAULT '', supersedes_notice_id INTEGER, total_qty INTEGER NOT NULL DEFAULT 0 CHECK(total_qty >= 0), total_amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(total_amount_minor >= 0), issued_at TEXT NOT NULL DEFAULT '', issued_by TEXT NOT NULL DEFAULT '', acknowledged_at TEXT NOT NULL DEFAULT '', acknowledged_by TEXT NOT NULL DEFAULT '', closed_at TEXT NOT NULL DEFAULT '', cancelled_at TEXT NOT NULL DEFAULT '', cancelled_by TEXT NOT NULL DEFAULT '', cancellation_reason TEXT NOT NULL DEFAULT '', payment_trigger_event_id INTEGER, remark TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(contract_id, notice_no, version), FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT, FOREIGN KEY(supersedes_notice_id) REFERENCES production_notices(id), FOREIGN KEY(payment_trigger_event_id) REFERENCES payment_trigger_events(id));",
        "DROP TABLE IF EXISTS production_notices;",
    ),
    (40, "CREATE INDEX IF NOT EXISTS idx_production_notices_contract ON production_notices(contract_id, status, notice_date DESC, id DESC);", "DROP INDEX IF EXISTS idx_production_notices_contract;"),
    (
        41,
        "CREATE TABLE IF NOT EXISTS production_notice_items (id INTEGER PRIMARY KEY AUTOINCREMENT, notice_id INTEGER NOT NULL, contract_item_id INTEGER NOT NULL, line_no INTEGER NOT NULL, item_name TEXT NOT NULL, spec_model TEXT NOT NULL DEFAULT '', drawing_no TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT '个', notice_qty INTEGER NOT NULL CHECK(notice_qty > 0), unit_price_minor INTEGER CHECK(unit_price_minor IS NULL OR unit_price_minor >= 0), amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(amount_minor >= 0), serial_start INTEGER, serial_end INTEGER, required_delivery_date TEXT NOT NULL DEFAULT '', remark TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(notice_id, line_no), UNIQUE(notice_id, contract_item_id), FOREIGN KEY(notice_id) REFERENCES production_notices(id) ON DELETE CASCADE, FOREIGN KEY(contract_item_id) REFERENCES contract_items(id) ON DELETE RESTRICT);",
        "DROP TABLE IF EXISTS production_notice_items;",
    ),
    (42, "CREATE INDEX IF NOT EXISTS idx_production_notice_items_contract_item ON production_notice_items(contract_item_id, notice_id);", "DROP INDEX IF EXISTS idx_production_notice_items_contract_item;"),
    (
        43,
        "CREATE TABLE IF NOT EXISTS production_notice_history (id INTEGER PRIMARY KEY AUTOINCREMENT, notice_id INTEGER NOT NULL, action TEXT NOT NULL, from_status TEXT NOT NULL DEFAULT '', to_status TEXT NOT NULL DEFAULT '', operator TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', snapshot_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, FOREIGN KEY(notice_id) REFERENCES production_notices(id) ON DELETE CASCADE);",
        "DROP TABLE IF EXISTS production_notice_history;",
    ),
    (44, "CREATE INDEX IF NOT EXISTS idx_production_history_notice ON production_notice_history(notice_id, created_at DESC, id DESC);", "DROP INDEX IF EXISTS idx_production_history_notice;"),
    (
        45,
        "CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_code TEXT NOT NULL DEFAULT '', invoice_no TEXT NOT NULL, invoice_type TEXT NOT NULL DEFAULT 'vat_special', issue_date TEXT NOT NULL DEFAULT '', received_date TEXT NOT NULL DEFAULT '', seller_name TEXT NOT NULL DEFAULT '', seller_tax_no TEXT NOT NULL DEFAULT '', buyer_name TEXT NOT NULL DEFAULT '', buyer_tax_no TEXT NOT NULL DEFAULT '', currency TEXT NOT NULL DEFAULT 'CNY', amount_ex_tax_minor INTEGER NOT NULL DEFAULT 0 CHECK(amount_ex_tax_minor >= 0), tax_amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(tax_amount_minor >= 0), total_amount_minor INTEGER NOT NULL DEFAULT 0 CHECK(total_amount_minor >= 0), tax_rate_bps INTEGER CHECK(tax_rate_bps IS NULL OR tax_rate_bps >= 0), invoice_status TEXT NOT NULL DEFAULT 'valid' CHECK(invoice_status IN ('valid','red','void')), review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','verified','exception')), deduction_status TEXT NOT NULL DEFAULT 'not_applicable' CHECK(deduction_status IN ('not_applicable','pending','deducted')), original_invoice_id INTEGER, remark TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(original_invoice_id) REFERENCES invoices(id));",
        "DROP TABLE IF EXISTS invoices;",
    ),
    (46, "CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_business_unique ON invoices(seller_tax_no, invoice_code, invoice_no) WHERE invoice_no != '';", "DROP INDEX IF EXISTS idx_invoices_business_unique;"),
    (47, "CREATE INDEX IF NOT EXISTS idx_invoices_status_date ON invoices(review_status, invoice_status, issue_date DESC, id DESC);", "DROP INDEX IF EXISTS idx_invoices_status_date;"),
    (
        48,
        "CREATE TABLE IF NOT EXISTS invoice_allocations (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, contract_id INTEGER NOT NULL, production_notice_id INTEGER, payment_plan_id INTEGER, allocated_amount_minor INTEGER NOT NULL CHECK(allocated_amount_minor > 0), remark TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE, FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT, FOREIGN KEY(production_notice_id) REFERENCES production_notices(id) ON DELETE RESTRICT, FOREIGN KEY(payment_plan_id) REFERENCES payment_plans(id) ON DELETE RESTRICT);",
        "DROP TABLE IF EXISTS invoice_allocations;",
    ),
    (49, "CREATE INDEX IF NOT EXISTS idx_invoice_allocations_contract ON invoice_allocations(contract_id, invoice_id);", "DROP INDEX IF EXISTS idx_invoice_allocations_contract;"),
    (50, "CREATE INDEX IF NOT EXISTS idx_invoice_allocations_notice ON invoice_allocations(production_notice_id) WHERE production_notice_id IS NOT NULL;", "DROP INDEX IF EXISTS idx_invoice_allocations_notice;"),
    (51, "CREATE INDEX IF NOT EXISTS idx_invoice_allocations_payment ON invoice_allocations(payment_plan_id) WHERE payment_plan_id IS NOT NULL;", "DROP INDEX IF EXISTS idx_invoice_allocations_payment;"),
    (
        52,
        "CREATE TABLE IF NOT EXISTS invoice_files (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, original_filename TEXT NOT NULL, storage_path TEXT NOT NULL, content_type TEXT NOT NULL DEFAULT '', file_size INTEGER NOT NULL DEFAULT 0 CHECK(file_size >= 0), sha256 TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE);",
        "DROP TABLE IF EXISTS invoice_files;",
    ),
    (53, "CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_files_hash ON invoice_files(invoice_id, sha256) WHERE sha256 != '';", "DROP INDEX IF EXISTS idx_invoice_files_hash;"),
    (
        54,
        "CREATE TABLE IF NOT EXISTS invoice_history (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL, action TEXT NOT NULL, operator TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', snapshot_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE);",
        "DROP TABLE IF EXISTS invoice_history;",
    ),
    (55, "CREATE INDEX IF NOT EXISTS idx_invoice_history_invoice ON invoice_history(invoice_id, created_at DESC, id DESC);", "DROP INDEX IF EXISTS idx_invoice_history_invoice;"),
    (
        56,
        "CREATE TABLE IF NOT EXISTS contract_item_history (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, item_id INTEGER, action TEXT NOT NULL, operator TEXT NOT NULL DEFAULT '', before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);",
        "DROP TABLE IF EXISTS contract_item_history;",
    ),
    (57, "CREATE INDEX IF NOT EXISTS idx_contract_item_history_contract ON contract_item_history(contract_id, created_at DESC, id DESC);", "DROP INDEX IF EXISTS idx_contract_item_history_contract;"),
    (
        58,
        "CREATE TRIGGER IF NOT EXISTS trg_production_notice_single_active_insert BEFORE INSERT ON production_notices WHEN NEW.status IN ('issued','acknowledged','closed') AND EXISTS (SELECT 1 FROM production_notices existing WHERE existing.contract_id = NEW.contract_id AND existing.notice_no = NEW.notice_no AND existing.status IN ('issued','acknowledged','closed')) BEGIN SELECT RAISE(ABORT, '同一投产通知只能有一个生效版本'); END;",
        "DROP TRIGGER IF EXISTS trg_production_notice_single_active_insert;",
    ),
    (
        59,
        "CREATE TRIGGER IF NOT EXISTS trg_production_notice_single_active_update BEFORE UPDATE OF status, notice_no, contract_id ON production_notices WHEN NEW.status IN ('issued','acknowledged','closed') AND EXISTS (SELECT 1 FROM production_notices existing WHERE existing.contract_id = NEW.contract_id AND existing.notice_no = NEW.notice_no AND existing.id != NEW.id AND existing.status IN ('issued','acknowledged','closed')) BEGIN SELECT RAISE(ABORT, '同一投产通知只能有一个生效版本'); END;",
        "DROP TRIGGER IF EXISTS trg_production_notice_single_active_update;",
    ),
    (60, "CREATE TABLE IF NOT EXISTS contract_serials (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, serial_no INTEGER NOT NULL CHECK(serial_no > 0), amount_minor INTEGER CHECK(amount_minor IS NULL OR amount_minor >= 0), status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')), remark TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(contract_id, serial_no), FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE);", "DROP TABLE IF EXISTS contract_serials;"),
    (61, "CREATE INDEX IF NOT EXISTS idx_contract_serials_contract ON contract_serials(contract_id, status, serial_no);", "DROP INDEX IF EXISTS idx_contract_serials_contract;"),
    (62, "ALTER TABLE payment_plans ADD COLUMN contract_serial_id INTEGER REFERENCES contract_serials(id);", "ALTER TABLE payment_plans DROP COLUMN contract_serial_id;"),
    (63, "CREATE INDEX IF NOT EXISTS idx_payment_serial ON payment_plans(contract_serial_id, due_date) WHERE contract_serial_id IS NOT NULL;", "DROP INDEX IF EXISTS idx_payment_serial;"),
] + invoice_constraints.INVOICE_CONSTRAINT_MIGRATIONS


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
