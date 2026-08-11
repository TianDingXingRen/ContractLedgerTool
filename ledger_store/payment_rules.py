"""Persistence and execution for contractual payment rules."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from . import money_fields
from .payment_plans import effective_invoice_allocation_minor


PARSE_STATUSES = {'exact', 'partial', 'conflict', 'unsupported', 'manual'}
RULE_TYPES = {'conditional', 'recurring'}
RULE_SCOPES = {
    'contract', 'production_notice', 'delivery_batch', 'settlement_period', 'other'
}
REPEAT_MODES = {'once', 'each_event'}
CONDITION_LOGICS = {'SINGLE', 'AND', 'OR', 'OTHER'}


def _json_list(value):
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    text = str(value or '[]').strip() or '[]'
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError('付款规则JSON字段无效') from exc
    if not isinstance(parsed, list):
        raise ValueError('付款规则JSON字段必须是数组')
    return json.dumps(parsed, ensure_ascii=False)


def _fingerprint(rule):
    value = '|'.join(str(rule.get(key) or '') for key in (
        'group_key', 'phase_name', 'source_text', 'ratio', 'amount_basis',
        'repeat_mode', 'trigger_event_type',
    ))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class PaymentRuleRepository:
    def __init__(self, *, get_conn, row_to_dict, now, validate_choice):
        self.get_conn = get_conn
        self.row_to_dict = row_to_dict
        self.now = now
        self.validate_choice = validate_choice

    def insert_impl(self, conn, contract_id, rule):
        now = self.now()
        rule_type = self.validate_choice(
            rule.get('rule_type') or 'conditional', RULE_TYPES, '付款规则类型'
        )
        scope = self.validate_choice(
            rule.get('scope') or 'contract', RULE_SCOPES, '付款规则范围'
        )
        repeat_mode = self.validate_choice(
            rule.get('repeat_mode') or 'once', REPEAT_MODES, '付款规则重复方式'
        )
        condition_logic = self.validate_choice(
            rule.get('condition_logic') or 'SINGLE', CONDITION_LOGICS, '付款条件逻辑'
        )
        parse_status = self.validate_choice(
            rule.get('parse_status') or 'manual', PARSE_STATUSES, '付款规则解析状态'
        )
        confirm_status = self.validate_choice(
            rule.get('confirm_status') or 'pending',
            {'pending', 'confirmed', 'void'},
            '付款规则确认状态',
        )
        ratio = rule.get('ratio')
        if ratio is not None:
            try:
                ratio = float(ratio)
            except (TypeError, ValueError) as exc:
                raise ValueError('付款规则比例必须是有效数字') from exc
            if not 0 <= ratio <= 100:
                raise ValueError('付款规则比例必须在 0 到 100 之间')
        explicit_minor, _ = money_fields.amount_pair(rule.get('explicit_amount'))
        calculated_minor, _ = money_fields.amount_pair(rule.get('calculated_amount'))
        fingerprint = str(rule.get('rule_fingerprint') or '').strip() or _fingerprint(rule)
        existing = conn.execute(
            'SELECT id FROM payment_rules WHERE contract_id = ? AND rule_fingerprint = ?',
            (contract_id, fingerprint),
        ).fetchone()
        if existing:
            return existing['id']
        cur = conn.execute(
            """
            INSERT INTO payment_rules (
                contract_id, group_key, phase_name, rule_type, scope,
                trigger_event_type, trigger_event, trigger_days, due_date,
                conditions_json, condition_logic, amount_basis, amount_basis_text,
                ratio, explicit_amount_minor, calculated_amount_minor, repeat_mode,
                source_text, source_block, rule_fingerprint, source_fingerprint,
                extractor_version, rule_version, parse_status, reason_codes_json,
                confirm_status, user_modified, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contract_id,
                rule.get('group_key') or '',
                rule.get('phase_name'),
                rule_type,
                scope,
                rule.get('trigger_event_type') or 'other',
                rule.get('trigger_event'),
                rule.get('trigger_days'),
                rule.get('due_date') or '',
                _json_list(rule.get('conditions_json') or rule.get('conditions')),
                condition_logic,
                rule.get('amount_basis') or 'unknown',
                rule.get('amount_basis_text') or '',
                ratio,
                explicit_minor,
                calculated_minor,
                repeat_mode,
                rule.get('source_text'),
                rule.get('source_block') or '',
                fingerprint,
                rule.get('source_fingerprint') or '',
                rule.get('extractor_version') or '',
                int(rule.get('rule_version') or 1),
                parse_status,
                _json_list(rule.get('reason_codes_json') or rule.get('reason_codes')),
                confirm_status,
                1 if rule.get('user_modified') else 0,
                now,
                now,
            ),
        )
        return cur.lastrowid

    def insert_many_impl(self, conn, contract_id, rules):
        mapping = {}
        for rule in rules or []:
            rule_id = self.insert_impl(conn, contract_id, rule)
            mapping[str(rule.get('rule_fingerprint') or '')] = rule_id
        return mapping

    def insert_many(self, contract_id, rules):
        with self.get_conn() as conn:
            return self.insert_many_impl(conn, contract_id, rules)

    @staticmethod
    def _public_rule(row):
        if row is None:
            return None
        result = dict(row)
        for public, minor in (
            ('explicit_amount', 'explicit_amount_minor'),
            ('calculated_amount', 'calculated_amount_minor'),
        ):
            result[public] = (
                None if result.get(minor) is None else result[minor] / 100
            )
        for key in ('conditions_json', 'reason_codes_json'):
            try:
                result[key.removesuffix('_json')] = json.loads(result.get(key) or '[]')
            except (TypeError, ValueError):
                result[key.removesuffix('_json')] = []
        return result

    def list(self, contract_id):
        with self.get_conn() as conn:
            rows = conn.execute(
                'SELECT * FROM payment_rules WHERE contract_id = ? '
                'ORDER BY group_key, id',
                (contract_id,),
            ).fetchall()
        return [self._public_rule(row) for row in rows]

    def get(self, rule_id, contract_id=None):
        sql = 'SELECT * FROM payment_rules WHERE id = ?'
        params = [rule_id]
        if contract_id is not None:
            sql += ' AND contract_id = ?'
            params.append(contract_id)
        with self.get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._public_rule(row)

    def set_confirm_status(self, rule_id, contract_id, status):
        status = self.validate_choice(
            status, {'pending', 'confirmed', 'void'}, '付款规则确认状态'
        )
        with self.get_conn() as conn:
            cur = conn.execute(
                'UPDATE payment_rules SET confirm_status = ?, updated_at = ? '
                'WHERE id = ? AND contract_id = ?',
                (status, self.now(), rule_id, contract_id),
            )
            return cur.rowcount

    def update_manual(self, rule_id, contract_id, data):
        repeat_mode = self.validate_choice(
            data.get('repeat_mode') or 'once', REPEAT_MODES, '付款规则重复方式'
        )
        scope = self.validate_choice(
            data.get('scope') or 'contract', RULE_SCOPES, '付款规则范围'
        )
        ratio = data.get('ratio')
        if ratio is not None and not 0 <= float(ratio) <= 100:
            raise ValueError('付款规则比例必须在0到100之间')
        explicit_minor, _ = money_fields.amount_pair(data.get('explicit_amount'))
        calculated_minor, _ = money_fields.amount_pair(data.get('calculated_amount'))
        with self.get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE payment_rules
                SET phase_name = ?, rule_type = ?, scope = ?,
                    trigger_event_type = ?, trigger_event = ?, trigger_days = ?,
                    amount_basis = ?, amount_basis_text = ?, ratio = ?,
                    explicit_amount_minor = ?, calculated_amount_minor = ?,
                    repeat_mode = ?, parse_status = 'manual',
                    reason_codes_json = '[]', confirm_status = 'pending',
                    user_modified = 1, rule_version = rule_version + 1,
                    updated_at = ?
                WHERE id = ? AND contract_id = ?
                """,
                (
                    data.get('phase_name') or '付款规则',
                    'recurring' if repeat_mode == 'each_event' else 'conditional',
                    scope,
                    data.get('trigger_event_type') or 'other',
                    data.get('trigger_event') or '',
                    data.get('trigger_days'),
                    data.get('amount_basis') or 'unknown',
                    data.get('amount_basis_text') or '',
                    ratio,
                    explicit_minor,
                    calculated_minor,
                    repeat_mode,
                    self.now(),
                    rule_id,
                    contract_id,
                ),
            )
            return cur.rowcount

    def create_event_instance(
        self,
        contract_id,
        rule_id,
        reference_no,
        event_date='',
        base_amount=None,
        reference_name='',
        metadata=None,
    ):
        reference_no = str(reference_no or '').strip()
        if not reference_no:
            raise ValueError('业务事件编号不能为空')
        base_minor, base_public = money_fields.amount_pair(base_amount)
        if base_minor is None or base_minor <= 0:
            raise ValueError('业务事件计算基数必须大于0')
        now = self.now()
        with self.get_conn() as conn:
            row = conn.execute(
                'SELECT * FROM payment_rules WHERE id = ? AND contract_id = ?',
                (rule_id, contract_id),
            ).fetchone()
            if not row:
                raise ValueError('付款规则不存在或不属于当前合同')
            rule = self._public_rule(row)
            if rule['confirm_status'] != 'confirmed':
                raise ValueError('请先确认付款规则，再生成付款实例')
            if rule['repeat_mode'] != 'each_event':
                raise ValueError('只有重复触发规则才能根据业务事件生成付款实例')
            if rule['parse_status'] in {'conflict', 'unsupported'}:
                raise ValueError('存在冲突或不支持的规则不能生成付款实例')
            if rule.get('ratio') is None:
                raise ValueError('付款规则缺少比例，无法计算付款金额')
            event_type = rule.get('trigger_event_type') or 'other'
            existing = conn.execute(
                'SELECT id FROM payment_trigger_events WHERE contract_id = ? '
                'AND event_type = ? AND reference_no = ?',
                (contract_id, event_type, reference_no),
            ).fetchone()
            if existing:
                event_id = existing['id']
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO payment_trigger_events (
                        contract_id, event_type, reference_no, event_date,
                        base_amount_minor, reference_name, metadata_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract_id, event_type, reference_no, event_date or '',
                        base_minor, reference_name or '',
                        json.dumps(metadata or {}, ensure_ascii=False), now, now,
                    ),
                )
                stored_event = conn.execute(
                    'SELECT id FROM payment_trigger_events WHERE contract_id = ? '
                    'AND event_type = ? AND reference_no = ?',
                    (contract_id, event_type, reference_no),
                ).fetchone()
                if not stored_event:
                    raise ValueError('业务事件保存失败')
                event_id = stored_event['id']
            instance_key = f'rule:{rule_id}:event:{event_id}'
            existing_plan = conn.execute(
                'SELECT id FROM payment_plans WHERE instance_key = ?',
                (instance_key,),
            ).fetchone()
            if existing_plan:
                return existing_plan['id'], False
            due_minor = int(
                (Decimal(base_minor) * Decimal(str(rule['ratio'])) / Decimal('100'))
                .quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            )
            due_amount = due_minor / 100
            contract = conn.execute(
                'SELECT subsystem_name FROM contracts WHERE id = ?',
                (contract_id,),
            ).fetchone()
            subsystem_name = str(
                contract['subsystem_name'] if contract else ''
            ).strip()[:120]
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO payment_plans (
                    contract_id, subsystem_name, phase_name, payment_type, trigger_event,
                    trigger_days, expected_trigger_date, due_date, ratio,
                    due_amount, due_amount_minor, paid_amount, paid_amount_minor,
                    paid_date, condition_text, source_text, confidence,
                    confirm_status, payment_status, remark, payment_rule_id,
                    trigger_event_id, instance_key, calculation_base_minor,
                    amount_basis, parse_status, reason_codes_json,
                    extractor_version, user_modified, created_at, updated_at
                ) VALUES (?, ?, ?, 'conditional', ?, ?, ?, '', ?, ?, ?, 0, 0,
                          '', ?, ?, ?, 'pending', 'unpaid', ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, 0, ?, ?)
                """,
                (
                    contract_id,
                    subsystem_name,
                    rule.get('phase_name') or '动态付款',
                    rule.get('trigger_event'),
                    rule.get('trigger_days'),
                    event_date or '',
                    rule.get('ratio'),
                    due_amount,
                    due_minor,
                    rule.get('source_text'),
                    rule.get('source_text'),
                    'high' if rule.get('parse_status') == 'exact' else 'medium',
                    f'来源事件：{reference_no}',
                    rule_id,
                    event_id,
                    instance_key,
                    base_minor,
                    rule.get('amount_basis') or '',
                    rule.get('parse_status') or 'partial',
                    rule.get('reason_codes_json') or '[]',
                    rule.get('extractor_version') or '',
                    now,
                    now,
                ),
            )
            stored_plan = conn.execute(
                'SELECT id FROM payment_plans WHERE instance_key = ?',
                (instance_key,),
            ).fetchone()
            if not stored_plan:
                raise ValueError('付款实例保存失败')
            return stored_plan['id'], cur.rowcount == 1

    def _upsert_matching_event(
        self, conn, *, contract_id, event_type, reference_no, event_date,
        base_amount_minor, reference_name, metadata, now,
    ):
        existing = conn.execute(
            """SELECT id, metadata_json FROM payment_trigger_events
               WHERE contract_id = ? AND event_type = ? AND reference_no = ?""",
            (contract_id, event_type, reference_no),
        ).fetchone()
        encoded_metadata = json.dumps(metadata or {}, ensure_ascii=False)
        if existing:
            try:
                existing_metadata = json.loads(existing['metadata_json'] or '{}')
            except (TypeError, ValueError):
                existing_metadata = {}
            incoming_notice_id = (metadata or {}).get('production_notice_id')
            if incoming_notice_id and (
                existing_metadata.get('production_notice_id') != incoming_notice_id
            ):
                raise ValueError('业务事件编号已被其他来源占用，请更换投产通知编号')
            conn.execute(
                """UPDATE payment_trigger_events
                   SET event_date = ?, base_amount_minor = ?, reference_name = ?,
                       metadata_json = ?, updated_at = ? WHERE id = ?""",
                (
                    event_date or '', base_amount_minor, reference_name or '',
                    encoded_metadata, now, existing['id'],
                ),
            )
            return existing['id']
        cur = conn.execute(
            """INSERT INTO payment_trigger_events (
                   contract_id, event_type, reference_no, event_date,
                   base_amount_minor, reference_name, metadata_json,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contract_id, event_type, reference_no, event_date or '',
                base_amount_minor, reference_name or '', encoded_metadata, now, now,
            ),
        )
        return cur.lastrowid

    @staticmethod
    def _sync_existing_plan(
        conn, instance_key, *, due_minor, base_amount_minor, ratio, event_date, now,
    ):
        plan = conn.execute(
            """SELECT id, due_amount_minor, calculation_base_minor,
                      paid_amount_minor, confirm_status
               FROM payment_plans WHERE instance_key = ?""",
            (instance_key,),
        ).fetchone()
        if not plan:
            return False
        changed = (
            plan['due_amount_minor'] != due_minor
            or plan['calculation_base_minor'] != base_amount_minor
        )
        if changed and plan['paid_amount_minor'] > 0:
            raise ValueError('业务事件金额已变化，但关联付款计划已经付款')
        if changed and plan['confirm_status'] == 'void':
            raise ValueError('业务事件金额已变化，但关联付款计划已经作废')
        if (
            changed
            and due_minor < effective_invoice_allocation_minor(conn, plan['id'])
        ):
            raise ValueError('应付金额不能小于付款计划的有效发票分摊金额')
        if changed:
            conn.execute(
                """UPDATE payment_plans
                   SET due_amount = ?, due_amount_minor = ?, ratio = ?,
                       calculation_base_minor = ?, expected_trigger_date = ?,
                       updated_at = ? WHERE id = ?""",
                (
                    due_minor / 100, due_minor, ratio, base_amount_minor,
                    event_date or '', now, plan['id'],
                ),
            )
        return True

    def create_matching_event_instances_impl(
        self,
        conn,
        *,
        contract_id,
        event_type,
        reference_no,
        event_date='',
        base_amount_minor=None,
        reference_name='',
        metadata=None,
    ):
        """Persist one business event and instantiate every matching rule.

        This transaction-aware entry point is used by upstream ledgers such as
        production notices.  The event and all generated payment instances are
        therefore committed or rolled back together.
        """
        reference_no = str(reference_no or '').strip()
        if not reference_no:
            raise ValueError('业务事件编号不能为空')
        if base_amount_minor is None or int(base_amount_minor) < 0:
            raise ValueError('业务事件计算基数不能小于 0')
        base_amount_minor = int(base_amount_minor)
        now = self.now()
        event_id = self._upsert_matching_event(
            conn, contract_id=contract_id, event_type=event_type,
            reference_no=reference_no, event_date=event_date,
            base_amount_minor=base_amount_minor, reference_name=reference_name,
            metadata=metadata, now=now,
        )

        rules = conn.execute(
            """
            SELECT * FROM payment_rules
            WHERE contract_id = ?
              AND confirm_status = 'confirmed'
              AND repeat_mode = 'each_event'
              AND scope = 'production_notice'
              AND trigger_event_type = ?
              AND parse_status NOT IN ('conflict','unsupported')
              AND ratio IS NOT NULL
            ORDER BY id
            """,
            (contract_id, event_type),
        ).fetchall()
        created_plan_ids = []
        contract = conn.execute(
            'SELECT subsystem_name FROM contracts WHERE id = ?',
            (contract_id,),
        ).fetchone()
        subsystem_name = str(
            contract['subsystem_name'] if contract else ''
        ).strip()[:120]
        for row in rules:
            rule = self._public_rule(row)
            instance_key = f'rule:{rule["id"]}:event:{event_id}'
            due_minor = int(
                (
                    Decimal(base_amount_minor)
                    * Decimal(str(rule['ratio']))
                    / Decimal('100')
                ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            )
            if self._sync_existing_plan(
                conn, instance_key, due_minor=due_minor,
                base_amount_minor=base_amount_minor, ratio=rule.get('ratio'),
                event_date=event_date, now=now,
            ):
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO payment_plans (
                    contract_id, subsystem_name, phase_name, payment_type, trigger_event,
                    trigger_days, expected_trigger_date, due_date, ratio,
                    due_amount, due_amount_minor, paid_amount, paid_amount_minor,
                    paid_date, condition_text, source_text, confidence,
                    confirm_status, payment_status, remark, payment_rule_id,
                    trigger_event_id, instance_key, calculation_base_minor,
                    amount_basis, parse_status, reason_codes_json,
                    extractor_version, user_modified, created_at, updated_at
                ) VALUES (?, ?, ?, 'conditional', ?, ?, ?, '', ?, ?, ?, 0, 0,
                          '', ?, ?, ?, 'pending', 'unpaid', ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, 0, ?, ?)
                """,
                (
                    contract_id,
                    subsystem_name,
                    rule.get('phase_name') or '动态付款',
                    rule.get('trigger_event'),
                    rule.get('trigger_days'),
                    event_date or '',
                    rule.get('ratio'),
                    due_minor / 100,
                    due_minor,
                    rule.get('source_text'),
                    rule.get('source_text'),
                    'high' if rule.get('parse_status') == 'exact' else 'medium',
                    f'来源事件：{reference_no}',
                    rule['id'],
                    event_id,
                    instance_key,
                    base_amount_minor,
                    rule.get('amount_basis') or '',
                    rule.get('parse_status') or 'partial',
                    rule.get('reason_codes_json') or '[]',
                    rule.get('extractor_version') or '',
                    now,
                    now,
                ),
            )
            if cur.rowcount == 1:
                created_plan_ids.append(cur.lastrowid)
        return event_id, created_plan_ids

    def list_events(self, contract_id):
        with self.get_conn() as conn:
            rows = conn.execute(
                'SELECT * FROM payment_trigger_events WHERE contract_id = ? '
                'ORDER BY event_date DESC, id DESC',
                (contract_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['base_amount'] = (
                None if item.get('base_amount_minor') is None
                else item['base_amount_minor'] / 100
            )
            result.append(item)
        return result
