"""Transactional contract field updates and range-ledger synchronization."""

from __future__ import annotations

import sqlite3


class ContractUpdateRepository:
    def __init__(
        self,
        *,
        get_conn,
        row_to_dict,
        now,
        amount_pair,
        validate_choice,
        contract_statuses,
        update_fields,
        contract_serials,
    ):
        self.get_conn = get_conn
        self.row_to_dict = row_to_dict
        self.now = now
        self.amount_pair = amount_pair
        self.validate_choice = validate_choice
        self.contract_statuses = contract_statuses
        self.update_fields = update_fields
        self.contract_serials = contract_serials

    def update(self, contract_id, data):
        assignments = []
        values = []
        for key in self.update_fields:
            if key not in data:
                continue
            if key == 'status':
                data[key] = self.validate_choice(
                    data[key], self.contract_statuses, '合同状态'
                )
            if key == 'amount':
                amount_minor, amount = self.amount_pair(data[key])
                data[key] = amount
                assignments.extend(['amount = ?', 'amount_minor = ?'])
                values.extend([amount, amount_minor])
                continue
            assignments.append(f'{key} = ?')
            values.append(data[key])
        if not assignments:
            return
        now = self.now()
        assignments.append('updated_at = ?')
        values.extend([now, contract_id])
        try:
            with self.get_conn() as conn:
                old_row = conn.execute(
                    'SELECT * FROM contracts WHERE id = ?', (contract_id,)
                ).fetchone()
                old_contract = self.row_to_dict(old_row)
                conn.execute(
                    f"UPDATE contracts SET {', '.join(assignments)} WHERE id = ?",
                    values,
                )
                self._sync_serial_range_if_needed(conn, contract_id, data, now)
                self._write_history(
                    conn, contract_id, old_contract, data, now
                )
        except sqlite3.IntegrityError as exc:
            detail = str(exc).lower()
            if 'contract_no' in detail or 'idx_contracts_contract_no_unique' in detail:
                raise ValueError('合同编号已存在') from exc
            raise

    def _sync_serial_range_if_needed(self, conn, contract_id, data, now):
        if 'coverage_start' not in data and 'coverage_end' not in data:
            return
        current_range = conn.execute(
            'SELECT coverage_start, coverage_end FROM contracts WHERE id = ?',
            (contract_id,),
        ).fetchone()
        if (
            current_range
            and current_range['coverage_start'] is not None
            and current_range['coverage_end'] is not None
        ):
            self.contract_serials.sync_range(contract_id, connection=conn)
            return
        conn.execute(
            """
            UPDATE contract_serials
               SET status = 'inactive', updated_at = ?
             WHERE contract_id = ?
            """,
            (now, contract_id),
        )

    def _write_history(self, conn, contract_id, old_contract, data, now):
        if not old_contract:
            return
        for key in self.update_fields:
            if key not in data:
                continue
            old_value = str(old_contract.get(key) or '')
            new_value = str(data[key] or '')
            if old_value == new_value:
                continue
            conn.execute(
                """
                INSERT INTO contract_history
                    (contract_id, field, old_value, new_value, changed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (contract_id, key, old_value, new_value, now),
            )
