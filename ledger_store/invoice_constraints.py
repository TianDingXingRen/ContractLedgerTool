"""Database-enforced invariants for full red-offset invoices."""

INVOICE_RED_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_original_active_red_unique
    ON invoices(original_invoice_id)
    WHERE invoice_status = 'red' AND original_invoice_id IS NOT NULL
"""

INVOICE_RED_INSERT_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_invoice_red_insert_consistency
BEFORE INSERT ON invoices
WHEN NEW.invoice_status = 'red'
 AND (
     NEW.original_invoice_id IS NULL
     OR NOT EXISTS (
         SELECT 1 FROM invoices original
         WHERE original.id = NEW.original_invoice_id
           AND original.invoice_status = 'valid'
           AND original.total_amount_minor = NEW.total_amount_minor
     )
 )
BEGIN
    SELECT RAISE(ABORT, '红字发票必须与有效原发票全额匹配');
END
"""

INVOICE_RED_UPDATE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_invoice_red_update_consistency
BEFORE UPDATE OF invoice_status, original_invoice_id, total_amount_minor ON invoices
WHEN NEW.invoice_status = 'red'
 AND (
     NEW.original_invoice_id IS NULL
     OR NOT EXISTS (
         SELECT 1 FROM invoices original
         WHERE original.id = NEW.original_invoice_id
           AND original.invoice_status = 'valid'
           AND original.total_amount_minor = NEW.total_amount_minor
     )
 )
BEGIN
    SELECT RAISE(ABORT, '红字发票必须与有效原发票全额匹配');
END
"""

INVOICE_ORIGINAL_UPDATE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_invoice_original_update_consistency
BEFORE UPDATE OF invoice_status, total_amount_minor ON invoices
WHEN EXISTS (
     SELECT 1 FROM invoices red
     WHERE red.original_invoice_id = OLD.id
       AND red.invoice_status = 'red'
 )
 AND (
     NEW.invoice_status != 'valid'
     OR EXISTS (
         SELECT 1 FROM invoices red
         WHERE red.original_invoice_id = OLD.id
           AND red.invoice_status = 'red'
           AND red.total_amount_minor != NEW.total_amount_minor
     )
 )
BEGIN
    SELECT RAISE(ABORT, '原发票已有生效红字发票，不能变更有效状态或价税合计');
END
"""

INVOICE_RED_CONSISTENCY_SQL = ';\n'.join((
    INVOICE_RED_UNIQUE_INDEX_SQL.strip(),
    INVOICE_RED_INSERT_TRIGGER_SQL.strip(),
    INVOICE_RED_UPDATE_TRIGGER_SQL.strip(),
    INVOICE_ORIGINAL_UPDATE_TRIGGER_SQL.strip(),
)) + ';'

INVOICE_CONSTRAINT_MIGRATIONS = [
    (
        64,
        INVOICE_RED_UNIQUE_INDEX_SQL,
        'DROP INDEX IF EXISTS idx_invoices_original_active_red_unique;',
    ),
    (
        65,
        INVOICE_RED_INSERT_TRIGGER_SQL,
        'DROP TRIGGER IF EXISTS trg_invoice_red_insert_consistency;',
    ),
    (
        66,
        INVOICE_RED_UPDATE_TRIGGER_SQL,
        'DROP TRIGGER IF EXISTS trg_invoice_red_update_consistency;',
    ),
    (
        67,
        INVOICE_ORIGINAL_UPDATE_TRIGGER_SQL,
        'DROP TRIGGER IF EXISTS trg_invoice_original_update_consistency;',
    ),
]
