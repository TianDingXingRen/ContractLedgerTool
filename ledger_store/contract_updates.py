"""Transactional contract field updates and range-ledger synchronization."""

from __future__ import annotations

import sqlite3

from core.domain_errors import ConflictError
from database.connection_factory import begin_immediate

from .contract_status_policy import assert_contracts_can_be_voided


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

    @staticmethod
    def _revision(value):
        if value is None:
            return None
        try:
            revision = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('合同版本无效，请刷新页面后重试') from exc
        if revision <= 0:
            raise ValueError('合同版本无效，请刷新页面后重试')
        return revision

    def update(self, contract_id, data, *, expected_revision=None):
        data = dict(data)
        expected_revision = self._revision(expected_revision)
        try:
            with self.get_conn() as conn:
                # The coverage choice is permanent.  Reserve the write slot
                # before reading so two requests cannot both validate the same
                # pending state and then overwrite one another.
                begin_immediate(conn)
                old_row = conn.execute(
                    'SELECT * FROM contracts WHERE id = ?', (contract_id,)
                ).fetchone()
                old_contract = self.row_to_dict(old_row)
                if not old_contract:
                    raise ValueError('合同记录不存在')
                current_revision = int(old_contract.get('revision') or 1)
                if (
                    expected_revision is not None
                    and current_revision != expected_revision
                ):
                    raise ConflictError(
                        '合同已被其他页面修改，已保留你的输入，请核对最新内容后再提交'
                    )
                self._validate_coverage_transition(old_contract, data)
                assignments, values = self._assignments(data)
                if not assignments:
                    return
                if (
                    data.get('status') == 'void'
                    and old_contract
                    and old_contract.get('status') != 'void'
                ):
                    assert_contracts_can_be_voided(conn, [contract_id])
                now = self.now()
                assignments.extend(['updated_at = ?', 'revision = revision + 1'])
                values.extend([now, contract_id, current_revision])
                cursor = conn.execute(
                    f"UPDATE contracts SET {', '.join(assignments)} "
                    "WHERE id = ? AND revision = ?",
                    values,
                )
                if cursor.rowcount == 0:
                    raise ConflictError(
                        '合同已被其他页面修改，已保留你的输入，请核对最新内容后再提交'
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

    def _assignments(self, data):
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
        return assignments, values

    @staticmethod
    def _coverage_flag(value):
        if value in (True, 1, '1'):
            return 1
        if value in (False, 0, '0', ''):
            return 0
        raise ValueError('发次适用状态无效')

    @staticmethod
    def _coverage_endpoint(value, label):
        if value is None or value == '':
            return None
        if isinstance(value, bool):
            raise ValueError(f'{label}必须是整数')
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{label}必须是整数') from exc
        if str(normalized) != str(value).strip() or not 1 <= normalized <= 1_000_000_000:
            raise ValueError(f'{label}必须是1到1000000000之间的整数')
        return normalized

    def _validate_coverage_transition(self, old_contract, data):
        if not old_contract:
            return
        relevant = {
            'project_name', 'coverage_not_applicable',
            'coverage_start', 'coverage_end',
        }
        if not relevant.intersection(data):
            return

        if 'coverage_not_applicable' in data:
            data['coverage_not_applicable'] = self._coverage_flag(
                data['coverage_not_applicable']
            )
        for key, label in (
            ('coverage_start', '起始发次'),
            ('coverage_end', '结束发次'),
        ):
            if key in data:
                data[key] = self._coverage_endpoint(data[key], label)

        old_not_applicable = bool(
            old_contract.get('coverage_not_applicable')
        )
        old_start = old_contract.get('coverage_start')
        old_end = old_contract.get('coverage_end')
        old_has_range = old_start is not None and old_end is not None

        new_not_applicable = bool(data.get(
            'coverage_not_applicable', old_not_applicable
        ))
        new_start = data.get('coverage_start', old_start)
        new_end = data.get('coverage_end', old_end)
        new_has_range = new_start is not None and new_end is not None

        if (new_start is None) != (new_end is None):
            raise ValueError('起始发次和结束发次需要同时填写')
        if new_not_applicable and new_has_range:
            raise ValueError('发次不适用时不能填写起始发次或结束发次')
        if new_has_range and new_start > new_end:
            raise ValueError('起始发次不能大于结束发次')

        project_name = str(data.get(
            'project_name', old_contract.get('project_name') or ''
        ) or '').strip()
        if new_has_range and not project_name:
            raise ValueError('填写发次范围前，请先填写项目名称')

        if old_not_applicable:
            if not new_not_applicable:
                raise ValueError('已选择发次不适用，不能改为数字范围')
            return
        if old_has_range:
            if new_not_applicable:
                raise ValueError('已有数字发次范围，不能改为不适用')
            if not new_has_range:
                raise ValueError('已有数字发次范围，不能清空适用状态')
            return

        # Pre-v70 rows with no endpoints are historical pending contracts.  A
        # coverage edit must make their first explicit, permanent choice.
        coverage_fields = {
            'coverage_not_applicable', 'coverage_start', 'coverage_end'
        }
        if coverage_fields.intersection(data) and not (
            new_not_applicable or new_has_range
        ):
            raise ValueError('待补发次合同必须选择数字范围或不适用')

    def _sync_serial_range_if_needed(self, conn, contract_id, data, now):
        if not {
            'coverage_not_applicable', 'coverage_start', 'coverage_end'
        }.intersection(data):
            return
        current_range = conn.execute(
            'SELECT coverage_not_applicable, coverage_start, coverage_end '
            'FROM contracts WHERE id = ?',
            (contract_id,),
        ).fetchone()
        if (
            current_range
            and not current_range['coverage_not_applicable']
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
            old_raw = old_contract.get(key)
            new_raw = data[key]
            old_value = '' if old_raw is None else str(old_raw)
            new_value = '' if new_raw is None else str(new_raw)
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
