"""Schema migration for invoice optimistic-lock revisions."""

INVOICE_REVISION_MIGRATIONS = [
    (
        71,
        "ALTER TABLE invoices ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0);",
        "ALTER TABLE invoices DROP COLUMN revision;",
    ),
]
