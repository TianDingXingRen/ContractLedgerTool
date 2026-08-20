"""Schema migration for contract optimistic-lock revisions."""

CONTRACT_REVISION_MIGRATIONS = [
    (
        72,
        "ALTER TABLE contracts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0);",
        "ALTER TABLE contracts DROP COLUMN revision;",
    ),
]
