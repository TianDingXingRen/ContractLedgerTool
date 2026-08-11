"""Schema migrations for contract classification and coverage fields."""


CLASSIFICATION_MIGRATIONS = [
    (
        68,
        "ALTER TABLE contracts ADD COLUMN subsystem_name TEXT DEFAULT '';",
        "ALTER TABLE contracts DROP COLUMN subsystem_name;",
    ),
    (
        69,
        "ALTER TABLE payment_plans ADD COLUMN subsystem_name TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE payment_plans DROP COLUMN subsystem_name;",
    ),
    (
        70,
        "ALTER TABLE contracts ADD COLUMN coverage_not_applicable INTEGER NOT NULL DEFAULT 0 CHECK(coverage_not_applicable IN (0,1));",
        "ALTER TABLE contracts DROP COLUMN coverage_not_applicable;",
    ),
]
