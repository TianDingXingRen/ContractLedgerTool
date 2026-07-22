"""Contract deletion, batch state changes, and history persistence."""

from __future__ import annotations


class ContractLifecycleRepository:
    def __init__(self, get_conn, now_func, validate_choice, statuses, row_to_dict):
        self._get_conn = get_conn
        self._now = now_func
        self._validate_choice = validate_choice
        self._statuses = statuses
        self._row_to_dict = row_to_dict

    @staticmethod
    def _has_procurement_refs(conn, contract_id):
        """Check shared procurement links, including partially initialized databases."""
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('project_contract_links', 'procurement_contract_refs')"
            ).fetchall()
        }
        for table_name in ('project_contract_links', 'procurement_contract_refs'):
            if table_name not in tables:
                continue
            if conn.execute(
                f'SELECT 1 FROM {table_name} WHERE contract_id = ? LIMIT 1',
                (contract_id,),
            ).fetchone():
                return True
        return False

    @staticmethod
    def _has_execution_refs(conn, contract_id):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('production_notices', 'invoice_allocations')"
            ).fetchall()
        }
        for table_name in ('production_notices', 'invoice_allocations'):
            if table_name in tables and conn.execute(
                f'SELECT 1 FROM {table_name} WHERE contract_id = ? LIMIT 1',
                (contract_id,),
            ).fetchone():
                return True
        return False

    def soft_delete(self, contract_id):
        now = self._now()
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE contracts SET deleted_at = ?, updated_at = ? "
                "WHERE id = ? AND (deleted_at = '' OR deleted_at IS NULL)",
                (now, now, contract_id),
            )
            if cur.rowcount:
                conn.execute(
                    """INSERT INTO contract_history
                       (contract_id, field, old_value, new_value, changed_at)
                       VALUES (?, 'deleted_at', '', ?, ?)""",
                    (contract_id, now, now),
                )
            return cur.rowcount

    def restore(self, contract_id):
        now = self._now()
        with self._get_conn() as conn:
            old = conn.execute(
                'SELECT deleted_at FROM contracts WHERE id = ?', (contract_id,)
            ).fetchone()
            cur = conn.execute(
                "UPDATE contracts SET deleted_at = '', updated_at = ? "
                "WHERE id = ? AND deleted_at != '' AND deleted_at IS NOT NULL",
                (now, contract_id),
            )
            if cur.rowcount:
                conn.execute(
                    """INSERT INTO contract_history
                       (contract_id, field, old_value, new_value, changed_at)
                       VALUES (?, 'deleted_at', ?, '', ?)""",
                    (contract_id, old[0] if old else '', now),
                )
            return cur.rowcount

    def permanently_delete(self, contract_id):
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM contracts WHERE id = ? "
                "AND deleted_at != '' AND deleted_at IS NOT NULL",
                (contract_id,),
            ).fetchone()
            if not row:
                return 0
            if self._has_procurement_refs(conn, contract_id):
                raise ValueError('该合同已关联采购项目，为保留审计记录不能永久删除')
            if self._has_execution_refs(conn, contract_id):
                raise ValueError('该合同已有投产通知或发票分摊，为保留审计记录不能永久删除')
            conn.execute('DELETE FROM contract_history WHERE contract_id = ?', (contract_id,))
            conn.execute('DELETE FROM payment_plans WHERE contract_id = ?', (contract_id,))
            conn.execute('DELETE FROM payment_trigger_events WHERE contract_id = ?', (contract_id,))
            conn.execute('DELETE FROM payment_rules WHERE contract_id = ?', (contract_id,))
            cur = conn.execute('DELETE FROM contracts WHERE id = ?', (contract_id,))
            return cur.rowcount

    def discard_unlinked(self, contract_id):
        with self._get_conn() as conn:
            if self._has_procurement_refs(conn, contract_id):
                raise ValueError('合同已建立采购关联，不能作为生成失败记录清理')
            if self._has_execution_refs(conn, contract_id):
                raise ValueError('合同已有投产通知或发票分摊，不能作为失败记录清理')
            conn.execute('DELETE FROM contract_history WHERE contract_id = ?', (contract_id,))
            conn.execute('DELETE FROM payment_plans WHERE contract_id = ?', (contract_id,))
            conn.execute('DELETE FROM payment_trigger_events WHERE contract_id = ?', (contract_id,))
            conn.execute('DELETE FROM payment_rules WHERE contract_id = ?', (contract_id,))
            cur = conn.execute('DELETE FROM contracts WHERE id = ?', (contract_id,))
            return cur.rowcount

    def batch_delete(self, ids):
        if not ids:
            return 0
        now = self._now()
        with self._get_conn() as conn:
            placeholders = ','.join('?' for _ in ids)
            cur = conn.execute(
                f"UPDATE contracts SET deleted_at = ?, updated_at = ? "
                f"WHERE id IN ({placeholders}) "
                "AND (deleted_at = '' OR deleted_at IS NULL)",
                [now, now] + ids,
            )
            return cur.rowcount

    def batch_update_status(self, ids, status):
        if not ids:
            return 0
        status = self._validate_choice(status, self._statuses, '合同状态')
        now = self._now()
        with self._get_conn() as conn:
            placeholders = ','.join('?' for _ in ids)
            old_rows = conn.execute(
                f'SELECT id, status FROM contracts WHERE id IN ({placeholders})', ids,
            ).fetchall()
            cur = conn.execute(
                f'UPDATE contracts SET status = ?, updated_at = ? '
                f'WHERE id IN ({placeholders})',
                [status, now] + ids,
            )
            for row in old_rows:
                if row['status'] == status:
                    continue
                conn.execute(
                    """INSERT INTO contract_history
                       (contract_id, field, old_value, new_value, changed_at)
                       VALUES (?, 'status', ?, ?, ?)""",
                    (row['id'], row['status'], status, now),
                )
            return cur.rowcount

    def history(self, contract_id):
        with self._get_conn() as conn:
            rows = conn.execute(
                'SELECT * FROM contract_history WHERE contract_id = ? '
                'ORDER BY changed_at DESC',
                (contract_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]
