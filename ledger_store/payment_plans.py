"""Payment-plan persistence isolated from the ledger compatibility facade."""

from __future__ import annotations

from . import list_queries, money_fields


class PaymentPlanRepository:
    """Own payment-plan validation and transactional persistence operations."""

    def __init__(
        self,
        *,
        get_conn,
        row_to_dict,
        now,
        validate_choice,
        payment_types,
        confidence_levels,
        confirm_statuses,
        payment_statuses,
        update_fields,
        field_validators,
    ):
        self.get_conn = get_conn
        self.row_to_dict = row_to_dict
        self.now = now
        self.validate_choice = validate_choice
        self.payment_types = payment_types
        self.confidence_levels = confidence_levels
        self.confirm_statuses = confirm_statuses
        self.payment_statuses = payment_statuses
        self.update_fields = update_fields
        self.field_validators = field_validators

    @staticmethod
    def normalize_consistency(plan):
        return money_fields.normalize_payment_consistency(plan)

    @staticmethod
    def append_assignment(assignments, values, key, row):
        money_fields.append_plan_assignment(assignments, values, key, row)

    @staticmethod
    def _validate_contract_serial(conn, contract_id, value):
        if value in (None, ''):
            return None
        try:
            serial_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('合同内编号无效') from exc
        row = conn.execute(
            """
            SELECT id
              FROM contract_serials
             WHERE id = ? AND contract_id = ? AND status = 'active'
            """,
            (serial_id, contract_id),
        ).fetchone()
        if not row:
            raise ValueError('合同内编号不存在、已停用或不属于当前合同')
        return serial_id

    def insert_impl(self, conn, contract_id, plan):
        plan = self.normalize_consistency(plan)
        contract_serial_id = self._validate_contract_serial(
            conn, contract_id, plan.get('contract_serial_id')
        )
        explicit_minor, explicit_amount = money_fields.amount_pair(
            plan.get('explicit_amount')
        )
        calculated_minor, calculated_amount = money_fields.amount_pair(
            plan.get('calculated_amount')
        )
        now = self.now()
        payment_type = self.validate_choice(
            plan.get('payment_type') or 'conditional',
            self.payment_types,
            '付款类型',
        )
        confidence = self.validate_choice(
            plan.get('confidence') or 'low', self.confidence_levels, '置信度'
        )
        confirm_status = self.validate_choice(
            plan.get('confirm_status') or 'pending',
            self.confirm_statuses,
            '确认状态',
        )
        payment_status = self.validate_choice(
            plan.get('payment_status') or 'unpaid',
            self.payment_statuses,
            '付款状态',
        )
        cur = conn.execute(
            """
            INSERT INTO payment_plans (
                contract_id, contract_serial_id, phase_name, payment_type,
                trigger_event, trigger_days,
                expected_trigger_date, due_date, ratio, due_amount, due_amount_minor,
                paid_amount, paid_amount_minor,
                paid_date, condition_text, source_text, confidence, confirm_status,
                payment_status, remark, payment_rule_id, trigger_event_id,
                instance_key, calculation_base_minor, amount_basis,
                explicit_amount_minor, calculated_amount_minor, parse_status,
                reason_codes_json, extractor_version, user_modified,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contract_id,
                contract_serial_id,
                plan.get('phase_name'),
                payment_type,
                plan.get('trigger_event'),
                plan.get('trigger_days'),
                plan.get('expected_trigger_date'),
                plan.get('due_date'),
                plan.get('ratio'),
                plan.get('due_amount'),
                plan.get('due_amount_minor'),
                plan.get('paid_amount') or 0,
                plan.get('paid_amount_minor') or 0,
                plan.get('paid_date'),
                plan.get('condition_text'),
                plan.get('source_text'),
                confidence,
                confirm_status,
                payment_status,
                plan.get('remark'),
                plan.get('payment_rule_id'),
                plan.get('trigger_event_id'),
                plan.get('instance_key') or '',
                plan.get('calculation_base_minor'),
                plan.get('amount_basis') or '',
                explicit_minor,
                calculated_minor,
                plan.get('parse_status') or 'manual',
                plan.get('reason_codes_json') or '[]',
                plan.get('extractor_version') or '',
                1 if plan.get('user_modified') else 0,
                now,
                now,
            ),
        )
        return cur.lastrowid

    def insert(self, contract_id, plan):
        with self.get_conn() as conn:
            return self.insert_impl(conn, contract_id, plan)

    def insert_many(self, contract_id, plans):
        if not plans:
            return []
        with self.get_conn() as conn:
            return [self.insert_impl(conn, contract_id, plan) for plan in plans]

    def save_changes(self, contract_id, changes):
        with self.get_conn() as conn:
            contract = conn.execute(
                'SELECT id FROM contracts WHERE id = ?', (contract_id,)
            ).fetchone()
            if not contract:
                raise ValueError('合同记录不存在')

            for change in changes:
                plan_id = change.get('id')
                if change.get('delete'):
                    if plan_id:
                        cur = conn.execute(
                            'DELETE FROM payment_plans WHERE id = ? AND contract_id = ?',
                            (plan_id, contract_id),
                        )
                        if cur.rowcount == 0:
                            raise ValueError('付款计划不存在或不属于当前合同')
                    continue

                incoming = change.get('data') or {}
                if plan_id:
                    existing = conn.execute(
                        'SELECT * FROM payment_plans WHERE id = ? AND contract_id = ?',
                        (plan_id, contract_id),
                    ).fetchone()
                    if not existing:
                        raise ValueError('付款计划不存在或不属于当前合同')
                    row = self.row_to_dict(existing)
                    row.update(incoming)
                    if 'contract_serial_id' in incoming:
                        row['contract_serial_id'] = self._validate_contract_serial(
                            conn, contract_id, incoming.get('contract_serial_id')
                        )
                    row['user_modified'] = 1
                    row['parse_status'] = 'manual'
                    row = self.normalize_consistency(row)
                    assignments = []
                    values = []
                    for key in self.update_fields:
                        if (
                            key not in incoming
                            and key not in {'payment_status', 'paid_date'}
                        ):
                            continue
                        if key in self.field_validators:
                            row[key] = self.validate_choice(
                                row[key], *self.field_validators[key]
                            )
                        self.append_assignment(assignments, values, key, row)
                    assignments.append('updated_at = ?')
                    assignments.extend(['user_modified = 1', "parse_status = 'manual'"])
                    values.extend([self.now(), plan_id, contract_id])
                    cur = conn.execute(
                        f"UPDATE payment_plans SET {', '.join(assignments)} "
                        "WHERE id = ? AND contract_id = ?",
                        values,
                    )
                    if cur.rowcount == 0:
                        raise ValueError('付款计划不存在或不属于当前合同')
                else:
                    self.insert_impl(conn, contract_id, incoming)

    def list(
        self,
        contract_id=None,
        confirm_status='',
        payment_status='',
        start_date='',
        end_date='',
        project_name='',
        page=0,
        per_page=20,
        limit=0,
    ):
        return list_queries.list_payment_plans(
            self.get_conn,
            self.row_to_dict,
            contract_id=contract_id,
            confirm_status=confirm_status,
            payment_status=payment_status,
            start_date=start_date,
            end_date=end_date,
            project_name=project_name,
            page=page,
            per_page=per_page,
            limit=limit,
        )

    def get(self, plan_id):
        with self.get_conn() as conn:
            row = conn.execute(
                """
                SELECT p.*, c.contract_no, c.title AS contract_title, c.counterparty,
                       c.owner, c.project_name, c.coverage_start, c.coverage_end,
                       s.serial_no, s.amount_minor AS serial_amount_minor,
                       s.status AS serial_status
                FROM payment_plans p
                JOIN contracts c ON c.id = p.contract_id
                LEFT JOIN contract_serials s ON s.id = p.contract_serial_id
                WHERE p.id = ? AND (c.deleted_at = '' OR c.deleted_at IS NULL)
                """,
                (plan_id,),
            ).fetchone()
        return self.row_to_dict(row)

    def update(self, plan_id, data, contract_id=None):
        if not any(key in data for key in self.update_fields):
            return None
        with self.get_conn() as conn:
            where = 'id = ?'
            lookup_values = [plan_id]
            if contract_id is not None:
                where += ' AND contract_id = ?'
                lookup_values.append(contract_id)
            existing = conn.execute(
                f'SELECT * FROM payment_plans WHERE {where}', lookup_values
            ).fetchone()
            if not existing:
                return 0
            merged = self.row_to_dict(existing)
            merged.update(
                {key: data[key] for key in self.update_fields if key in data}
            )
            if 'contract_serial_id' in data:
                merged['contract_serial_id'] = self._validate_contract_serial(
                    conn, existing['contract_id'], data.get('contract_serial_id')
                )
            merged = self.normalize_consistency(merged)
            assignments = []
            values = []
            for key in self.update_fields:
                if key not in data and key not in {'payment_status', 'paid_date'}:
                    continue
                if key in self.field_validators:
                    merged[key] = self.validate_choice(
                        merged[key], *self.field_validators[key]
                    )
                self.append_assignment(assignments, values, key, merged)
            assignments.append('updated_at = ?')
            values.append(self.now())
            values.extend(lookup_values)
            cur = conn.execute(
                f"UPDATE payment_plans SET {', '.join(assignments)} WHERE {where}",
                values,
            )
            return cur.rowcount

    def batch_confirm(self, plan_ids, contract_id=None):
        if not plan_ids:
            return 0
        now = self.now()
        with self.get_conn() as conn:
            count = 0
            for plan_id in plan_ids:
                where = 'id = ? AND confirm_status = ?'
                params = [plan_id, 'pending']
                if contract_id is not None:
                    where += ' AND contract_id = ?'
                    params.append(contract_id)
                cur = conn.execute(
                    "UPDATE payment_plans SET confirm_status = 'confirmed', "
                    f"updated_at = ? WHERE {where}",
                    [now] + params,
                )
                count += cur.rowcount
            return count

    def batch_mark_paid(self, plan_ids, paid_date):
        if not plan_ids:
            return 0
        now = self.now()
        with self.get_conn() as conn:
            count = 0
            for plan_id in plan_ids:
                row = conn.execute(
                    """SELECT * FROM payment_plans
                       WHERE id = ? AND confirm_status = 'confirmed'
                         AND payment_status != 'paid'""",
                    (plan_id,),
                ).fetchone()
                if not row:
                    continue
                plan = self.row_to_dict(row)
                due_amount = plan.get('due_amount')
                if due_amount is None:
                    continue
                updated = self.normalize_consistency(
                    {**plan, 'paid_amount': due_amount, 'paid_date': paid_date}
                )
                cur = conn.execute(
                    """UPDATE payment_plans
                       SET paid_amount = ?, paid_amount_minor = ?, paid_date = ?,
                           payment_status = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        updated['paid_amount'],
                        updated['paid_amount_minor'],
                        updated['paid_date'],
                        updated['payment_status'],
                        now,
                        plan_id,
                    ),
                )
                count += cur.rowcount
            return count

    def delete(self, plan_id, contract_id=None):
        sql = 'DELETE FROM payment_plans WHERE id = ?'
        params = [plan_id]
        if contract_id is not None:
            sql += ' AND contract_id = ?'
            params.append(contract_id)
        with self.get_conn() as conn:
            conn.execute(sql, params)
