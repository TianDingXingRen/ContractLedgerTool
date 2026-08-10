"""Schema SQL and lightweight migrations for procurement persistence."""

CURRENT_SCHEMA_VERSION = 5

PROCUREMENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS procurement_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_no TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL,
    purchase_method TEXT NOT NULL DEFAULT 'competitive_negotiation',
    demand_department TEXT DEFAULT '',
    owner TEXT DEFAULT '',
    budget_minor INTEGER,
    target_price_minor INTEGER,
    currency TEXT NOT NULL DEFAULT 'CNY',
    delivery_place TEXT DEFAULT '',
    delivery_requirement TEXT DEFAULT '',
    payment_requirement TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','documents_ready','inquiry_sent','quotes_received',
            'clarifying','negotiating','award_draft','award_confirmed',
            'contract_draft','contract_created','archived')),
    remark TEXT DEFAULT '',
    archived_at TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    spec_model TEXT DEFAULT '',
    drawing_no TEXT DEFAULT '',
    quantity_text TEXT NOT NULL,
    unit TEXT NOT NULL,
    required_delivery_date TEXT DEFAULT '',
    technical_requirement TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, line_no),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    supplier_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    contact_phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    direct_support_experience TEXT DEFAULT '',
    aerospace_support_experience TEXT DEFAULT '',
    qualifications TEXT DEFAULT '',
    invite_status TEXT NOT NULL DEFAULT 'pending',
    quote_status TEXT NOT NULL DEFAULT 'pending',
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, normalized_name),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    original_name TEXT DEFAULT '',
    sha256 TEXT DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, file_type, relative_path),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quote_import_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    quote_round INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'parsed'
        CHECK(status IN ('parsed','invalid','confirmed','cancelled')),
    created_at TEXT NOT NULL,
    confirmed_at TEXT DEFAULT '',
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS quote_mapping_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    quote_round INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    source_json TEXT NOT NULL,
    column_map_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'mapping'
        CHECK(status IN ('mapping','parsed','invalid','confirmed','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_quote_import_hash
    ON quote_import_jobs(project_id, file_sha256);

CREATE TABLE IF NOT EXISTS supplier_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    quote_round INTEGER NOT NULL,
    quote_date TEXT DEFAULT '',
    quote_valid_until TEXT DEFAULT '',
    total_amount_minor INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'CNY',
    tax_rate_bps INTEGER,
    price_basis TEXT NOT NULL DEFAULT 'tax_inclusive',
    delivery_period TEXT DEFAULT '',
    payment_terms TEXT DEFAULT '',
    warranty_period TEXT DEFAULT '',
    package_transport TEXT DEFAULT '',
    technical_deviation TEXT DEFAULT '',
    commercial_deviation TEXT DEFAULT '',
    original_file_id INTEGER,
    import_job_id INTEGER,
    status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK(status IN ('confirmed','superseded','rejected')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, supplier_id, quote_round),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE RESTRICT,
    FOREIGN KEY(original_file_id) REFERENCES project_files(id) ON DELETE SET NULL,
    FOREIGN KEY(import_job_id) REFERENCES quote_import_jobs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS supplier_quote_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id INTEGER NOT NULL,
    project_item_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    spec_model TEXT DEFAULT '',
    drawing_no TEXT DEFAULT '',
    quantity_text TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price_minor INTEGER NOT NULL,
    amount_minor INTEGER NOT NULL,
    delivery_period TEXT DEFAULT '',
    technical_deviation TEXT DEFAULT '',
    commercial_deviation TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(quote_id, project_item_id),
    FOREIGN KEY(quote_id) REFERENCES supplier_quotes(id) ON DELETE CASCADE,
    FOREIGN KEY(project_item_id) REFERENCES project_items(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS comparison_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    quote_ids_json TEXT NOT NULL,
    rule_config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comparison_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comparison_run_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    project_item_id INTEGER,
    supplier_id INTEGER,
    quote_id INTEGER,
    result_type TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    suggestion TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','confirmed','ignored')),
    metric_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(comparison_run_id) REFERENCES comparison_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(project_item_id) REFERENCES project_items(id) ON DELETE SET NULL,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE SET NULL,
    FOREIGN KEY(quote_id) REFERENCES supplier_quotes(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_comparison_project
    ON comparison_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comparison_result_run
    ON comparison_results(comparison_run_id, result_type);

CREATE TABLE IF NOT EXISTS clarification_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    supplier_id INTEGER,
    project_item_id INTEGER,
    question_type TEXT NOT NULL,
    question_text TEXT NOT NULL,
    source_result_id INTEGER,
    answer_text TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','confirmed','sent','replied','closed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_result_id),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE SET NULL,
    FOREIGN KEY(project_item_id) REFERENCES project_items(id) ON DELETE SET NULL,
    FOREIGN KEY(source_result_id) REFERENCES comparison_results(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS negotiation_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    round_no INTEGER NOT NULL,
    meeting_date TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, round_no),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS negotiation_commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    quote_id INTEGER,
    quote_amount_minor INTEGER,
    delivery_period TEXT DEFAULT '',
    payment_terms TEXT DEFAULT '',
    commitment TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(round_id, supplier_id),
    FOREIGN KEY(round_id) REFERENCES negotiation_rounds(id) ON DELETE CASCADE,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE RESTRICT,
    FOREIGN KEY(quote_id) REFERENCES supplier_quotes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS procurement_rule_configs (
    project_id INTEGER PRIMARY KEY,
    price_threshold_percent TEXT NOT NULL DEFAULT '20',
    min_valid_suppliers INTEGER NOT NULL DEFAULT 2,
    require_same_price_basis INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS award_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    quote_id INTEGER NOT NULL,
    recommended_amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CNY',
    reason_summary TEXT NOT NULL,
    price_reason TEXT DEFAULT '',
    technical_reason TEXT DEFAULT '',
    commercial_reason TEXT DEFAULT '',
    delivery_reason TEXT DEFAULT '',
    risk_note TEXT DEFAULT '',
    lowest_price_not_selected_reason TEXT DEFAULT '',
    contract_notice TEXT DEFAULT '',
    is_split INTEGER NOT NULL DEFAULT 0,
    supplier_summary TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','confirmed','converted','superseded')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, version),
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(supplier_id) REFERENCES project_suppliers(id) ON DELETE RESTRICT,
    FOREIGN KEY(quote_id) REFERENCES supplier_quotes(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS award_recommendation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL,
    project_item_id INTEGER NOT NULL,
    quote_item_id INTEGER NOT NULL,
    supplier_id INTEGER,
    quote_id INTEGER,
    item_name TEXT NOT NULL,
    spec_model TEXT DEFAULT '',
    quantity_text TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price_minor INTEGER NOT NULL,
    amount_minor INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(recommendation_id, project_item_id),
    FOREIGN KEY(recommendation_id) REFERENCES award_recommendations(id) ON DELETE CASCADE,
    FOREIGN KEY(project_item_id) REFERENCES project_items(id) ON DELETE RESTRICT,
    FOREIGN KEY(quote_item_id) REFERENCES supplier_quote_items(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS contract_data_sheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    recommendation_id INTEGER NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','in_editor','completed','failed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE CASCADE,
    FOREIGN KEY(recommendation_id) REFERENCES award_recommendations(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS project_contract_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    recommendation_id INTEGER NOT NULL,
    data_sheet_id INTEGER NOT NULL UNIQUE,
    contract_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE RESTRICT,
    FOREIGN KEY(recommendation_id) REFERENCES award_recommendations(id) ON DELETE RESTRICT,
    FOREIGN KEY(data_sheet_id) REFERENCES contract_data_sheets(id) ON DELETE RESTRICT,
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS procurement_contract_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    contract_id INTEGER NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'direct_contract',
    source_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE RESTRICT,
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS procurement_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT DEFAULT '',
    after_json TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_procurement_project_status
    ON procurement_projects(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_quote_project
    ON supplier_quotes(project_id, supplier_id, quote_round DESC);
CREATE INDEX IF NOT EXISTS idx_clarification_project
    ON clarification_questions(project_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_procurement_audit_entity
    ON procurement_audit_events(entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_procurement_contract_refs_project
    ON procurement_contract_refs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_procurement_project_updated
    ON procurement_projects(updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_project_files_created
    ON project_files(project_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS procurement_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


SCHEMA_VERSION_INSERT_SQL = (
    "INSERT OR IGNORE INTO procurement_schema_version(version, applied_at) VALUES (?, ?)"
)


V2_COLUMN_MIGRATIONS = [
    ('award_recommendations', 'is_split', 'INTEGER NOT NULL DEFAULT 0'),
    ('award_recommendations', 'supplier_summary', "TEXT DEFAULT ''"),
    ('award_recommendation_items', 'supplier_id', 'INTEGER'),
    ('award_recommendation_items', 'quote_id', 'INTEGER'),
]


V3_CONTRACT_REFS_SQL = """
CREATE TABLE IF NOT EXISTS procurement_contract_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    contract_id INTEGER NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'direct_contract',
    source_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES procurement_projects(id) ON DELETE RESTRICT,
    FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE RESTRICT
)
"""


V3_CONTRACT_REFS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_procurement_contract_refs_project
   ON procurement_contract_refs(project_id, created_at DESC)
"""


V4_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_procurement_project_updated "
    "ON procurement_projects(updated_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_project_files_created "
    "ON project_files(project_id, created_at DESC, id DESC)",
)


V5_SUPPLIER_COLUMN_MIGRATIONS = [
    ('project_suppliers', 'direct_support_experience', "TEXT DEFAULT ''"),
    ('project_suppliers', 'aerospace_support_experience', "TEXT DEFAULT ''"),
    ('project_suppliers', 'qualifications', "TEXT DEFAULT ''"),
]
