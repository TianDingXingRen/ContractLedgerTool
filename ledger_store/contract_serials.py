"""Contract-number ledger independent from production notices."""

from __future__ import annotations

from utils.money import to_minor
from utils.security import limit_text


MAX_SERIALS_PER_CONTRACT = 5000


class ContractSerialRepository:
    """Maintain one auditable amount record for every number in a contract range."""

    def __init__(self, *, get_conn, row_to_dict, now):
        self.get_conn = get_conn
        self.row_to_dict = row_to_dict
        self.now = now

    @staticmethod
    def _validated_range(contract):
        if not contract:
            raise ValueError('合同记录不存在')
        start = contract['coverage_start']
        end = contract['coverage_end']
        if start is None or end is None:
            raise ValueError('请先维护合同覆盖起始号和结束号')
        start, end = int(start), int(end)
        if start <= 0 or end < start:
            raise ValueError('合同覆盖号段无效')
        if end - start + 1 > MAX_SERIALS_PER_CONTRACT:
            raise ValueError(f'单个合同最多维护 {MAX_SERIALS_PER_CONTRACT} 个编号')
        return start, end

    def sync_range(self, contract_id, *, connection=None):
        """Insert missing numbers and inactivate records outside the current range."""

        def execute(conn):
            contract = conn.execute(
                'SELECT id, coverage_start, coverage_end FROM contracts WHERE id = ?',
                (contract_id,),
            ).fetchone()
            start, end = self._validated_range(contract)
            now = self.now()
            conn.executemany(
                """
                INSERT OR IGNORE INTO contract_serials
                    (contract_id, serial_no, amount_minor, status, remark,
                     created_at, updated_at)
                VALUES (?, ?, NULL, 'active', '', ?, ?)
                """,
                [(contract_id, number, now, now) for number in range(start, end + 1)],
            )
            conn.execute(
                """
                UPDATE contract_serials
                   SET status = CASE
                         WHEN serial_no BETWEEN ? AND ? THEN 'active'
                         ELSE 'inactive'
                       END,
                       updated_at = ?
                 WHERE contract_id = ?
                """,
                (start, end, now, contract_id),
            )
            return end - start + 1

        if connection is not None:
            return execute(connection)
        with self.get_conn() as conn:
            return execute(conn)

    def list(self, contract_id, *, include_inactive=False):
        status_clause = '' if include_inactive else "AND s.status = 'active'"
        with self.get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT s.*,
                       s.amount_minor AS serial_amount_minor,
                       COUNT(p.id) AS payment_plan_count
                  FROM contract_serials s
                  LEFT JOIN payment_plans p ON p.contract_serial_id = s.id
                 WHERE s.contract_id = ? {status_clause}
                 GROUP BY s.id
                 ORDER BY s.serial_no
                """,
                (contract_id,),
            ).fetchall()
        return [self.row_to_dict(row) for row in rows]

    def get(self, serial_id, *, contract_id=None):
        sql = """
            SELECT s.*, s.amount_minor AS serial_amount_minor
              FROM contract_serials s
             WHERE s.id = ?
        """
        params = [serial_id]
        if contract_id is not None:
            sql += ' AND s.contract_id = ?'
            params.append(contract_id)
        with self.get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return self.row_to_dict(row)

    def save_amounts(self, contract_id, entries):
        if len(entries) > MAX_SERIALS_PER_CONTRACT:
            raise ValueError(f'单次最多维护 {MAX_SERIALS_PER_CONTRACT} 个编号')
        seen = set()
        now = self.now()
        with self.get_conn() as conn:
            for entry in entries:
                try:
                    serial_id = int(entry.get('id'))
                except (TypeError, ValueError) as exc:
                    raise ValueError('合同内编号记录无效') from exc
                if serial_id in seen:
                    raise ValueError('合同内编号记录重复')
                seen.add(serial_id)
                amount_minor = to_minor(entry.get('amount'))
                if amount_minor is not None and amount_minor < 0:
                    raise ValueError('本编号金额不能为负数')
                remark = limit_text(str(entry.get('remark') or '').strip(), 500)
                cur = conn.execute(
                    """
                    UPDATE contract_serials
                       SET amount_minor = ?, remark = ?, updated_at = ?
                     WHERE id = ? AND contract_id = ?
                    """,
                    (amount_minor, remark, now, serial_id, contract_id),
                )
                if cur.rowcount == 0:
                    raise ValueError('合同内编号不存在或不属于当前合同')
        return len(entries)

    def set_bulk_amount(self, contract_id, amount, *, blank_only=True):
        amount_minor = to_minor(amount, allow_none=False)
        if amount_minor < 0:
            raise ValueError('本编号金额不能为负数')
        blank_clause = ' AND amount_minor IS NULL' if blank_only else ''
        with self.get_conn() as conn:
            cur = conn.execute(
                f"""
                UPDATE contract_serials
                   SET amount_minor = ?, updated_at = ?
                 WHERE contract_id = ? AND status = 'active' {blank_clause}
                """,
                (amount_minor, self.now(), contract_id),
            )
            return cur.rowcount
