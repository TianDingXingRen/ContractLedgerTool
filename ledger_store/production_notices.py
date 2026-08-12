"""Production notice ledger, quantity controls, and payment-event linkage."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from database.connection_factory import begin_immediate
from .production_notice_guards import (
    active_contract,
    ensure_event_has_no_payment,
    ensure_notice_has_no_invoice_allocations,
    require_conditional_update,
)


ACTIVE_NOTICE_STATUSES = {'issued', 'acknowledged', 'closed'}


class ProductionNoticeRepository:
    def __init__(self, *, get_conn, now, payment_rules):
        self.get_conn = get_conn
        self.now = now
        self.payment_rules = payment_rules

    @staticmethod
    def _public(row):
        if row is None:
            return None
        result = dict(row)
        if 'total_amount_minor' in result:
            result['total_amount'] = (result.get('total_amount_minor') or 0) / 100
        if 'unit_price_minor' in result:
            result['unit_price'] = (
                None if result.get('unit_price_minor') is None
                else result['unit_price_minor'] / 100
            )
        if 'amount_minor' in result:
            result['amount'] = (result.get('amount_minor') or 0) / 100
        if 'allocated_amount_minor' in result:
            result['allocated_amount'] = (result.get('allocated_amount_minor') or 0) / 100
        return result

    def _next_notice_no(self, conn):
        prefix = f'TZ-{date.today().strftime("%Y%m%d")}-'
        row = conn.execute(
            'SELECT notice_no FROM production_notices WHERE notice_no LIKE ? '
            'ORDER BY notice_no DESC LIMIT 1',
            (f'{prefix}%',),
        ).fetchone()
        sequence = 1
        if row:
            try:
                sequence = int(row['notice_no'].rsplit('-', 1)[-1]) + 1
            except (TypeError, ValueError):
                sequence = 1
        return f'{prefix}{sequence:03d}'

    def list(self, contract_id=None, status='', page=0, per_page=50):
        conditions = []
        params = []
        if contract_id is not None:
            conditions.append('pn.contract_id = ?')
            params.append(contract_id)
        if status:
            conditions.append('pn.status = ?')
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        sql = f"""
                SELECT pn.*, c.contract_no, c.title AS contract_title,
                       COALESCE((SELECT SUM(ia.allocated_amount_minor)
                                 FROM invoice_allocations ia
                                 JOIN invoices i ON i.id = ia.invoice_id
                                 WHERE ia.production_notice_id = pn.id
                                   AND i.invoice_status = 'valid'
                                   AND NOT EXISTS (
                                       SELECT 1 FROM invoices red
                                       WHERE red.original_invoice_id = i.id
                                         AND red.invoice_status = 'red'
                                   )), 0)
                           AS allocated_amount_minor
                FROM production_notices pn
                JOIN contracts c ON c.id = pn.contract_id
                {where}
                ORDER BY pn.notice_date DESC, pn.id DESC
                """
        query_params = list(params)
        total = None
        if page > 0:
            with self.get_conn() as conn:
                total = conn.execute(
                    f"""SELECT COUNT(*) FROM production_notices pn
                         JOIN contracts c ON c.id = pn.contract_id {where}""",
                    params,
                ).fetchone()[0]
            sql += ' LIMIT ? OFFSET ?'
            query_params.extend([per_page, max(0, (page - 1) * per_page)])
        with self.get_conn() as conn:
            rows = conn.execute(sql, query_params).fetchall()
        public_rows = [self._public(row) for row in rows]
        if page <= 0:
            return public_rows
        return {
            'rows': public_rows,
            'total': total,
            'page': page,
            'pages': (total + per_page - 1) // per_page or 1,
            'per_page': per_page,
        }

    def summary(self, contract_id=None, status=''):
        conditions = []
        params = []
        if contract_id is not None:
            conditions.append('contract_id = ?')
            params.append(contract_id)
        if status:
            conditions.append('status = ?')
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        with self.get_conn() as conn:
            row = conn.execute(
                f"""SELECT COUNT(*),
                           SUM(CASE WHEN status IN ('issued','acknowledged')
                                    THEN 1 ELSE 0 END),
                           COALESCE(SUM(CASE WHEN status IN ('issued','acknowledged','closed')
                                             THEN total_qty ELSE 0 END), 0),
                           COALESCE(SUM(CASE WHEN status IN ('issued','acknowledged','closed')
                                             THEN total_amount_minor ELSE 0 END), 0)
                      FROM production_notices {where}""",
                params,
            ).fetchone()
        return {
            'count': row[0] or 0,
            'active_count': row[1] or 0,
            'total_qty': row[2] or 0,
            'total_amount': float(row[3] or 0) / 100,
        }

    def get(self, notice_id):
        with self.get_conn() as conn:
            row = conn.execute(
                """
                SELECT pn.*, c.contract_no, c.title AS contract_title,
                       c.counterparty AS contract_counterparty,
                       c.status AS contract_status,
                       COALESCE((SELECT SUM(ia.allocated_amount_minor)
                                 FROM invoice_allocations ia
                                 JOIN invoices i ON i.id = ia.invoice_id
                                 WHERE ia.production_notice_id = pn.id
                                   AND i.invoice_status = 'valid'
                                   AND NOT EXISTS (
                                       SELECT 1 FROM invoices red
                                       WHERE red.original_invoice_id = i.id
                                         AND red.invoice_status = 'red'
                                   )), 0)
                           AS allocated_amount_minor
                FROM production_notices pn
                JOIN contracts c ON c.id = pn.contract_id
                WHERE pn.id = ?
                """,
                (notice_id,),
            ).fetchone()
            if not row:
                return None
            item_rows = conn.execute(
                """SELECT pni.*, ci.contracted_qty,
                          COALESCE((SELECT SUM(other.notice_qty)
                                    FROM production_notice_items other
                                    JOIN production_notices opn ON opn.id = other.notice_id
                                    WHERE other.contract_item_id = pni.contract_item_id
                                      AND opn.status IN ('issued','acknowledged','closed')), 0)
                              AS cumulative_issued_qty
                   FROM production_notice_items pni
                   JOIN contract_items ci ON ci.id = pni.contract_item_id
                   WHERE pni.notice_id = ? ORDER BY pni.line_no, pni.id""",
                (notice_id,),
            ).fetchall()
            history = conn.execute(
                'SELECT * FROM production_notice_history WHERE notice_id = ? '
                'ORDER BY created_at DESC, id DESC',
                (notice_id,),
            ).fetchall()
        result = self._public(row)
        result['items'] = [self._public(item) for item in item_rows]
        result['history'] = [dict(item) for item in history]
        return result

    def _snapshot(self, conn, notice_id):
        notice = conn.execute(
            'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
        ).fetchone()
        items = conn.execute(
            'SELECT * FROM production_notice_items WHERE notice_id = ? ORDER BY line_no',
            (notice_id,),
        ).fetchall()
        return json.dumps(
            {'notice': dict(notice) if notice else {}, 'items': [dict(row) for row in items]},
            ensure_ascii=False,
        )

    def _history(self, conn, notice_id, action, from_status='', to_status='', operator='', note=''):
        conn.execute(
            """INSERT INTO production_notice_history (
                   notice_id, action, from_status, to_status, operator, note,
                   snapshot_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                notice_id, action, from_status or '', to_status or '',
                operator or '', note or '', self._snapshot(conn, notice_id), self.now(),
            ),
        )

    @staticmethod
    def _parse_item_rows(conn, contract_id, rows):
        parsed = []
        seen = set()
        for index, raw in enumerate(rows or [], start=1):
            qty_text = str(raw.get('notice_qty') or '').strip()
            if not qty_text:
                continue
            try:
                qty = int(qty_text)
            except (TypeError, ValueError) as exc:
                raise ValueError('投产数量必须是正整数') from exc
            if qty <= 0 or str(qty) != qty_text.lstrip('+'):
                raise ValueError('投产数量必须是正整数')
            try:
                contract_item_id = int(raw.get('contract_item_id') or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError('投产通知产品无效') from exc
            if not contract_item_id or contract_item_id in seen:
                raise ValueError('同一份投产通知不能重复选择同一个合同产品')
            seen.add(contract_item_id)
            baseline = conn.execute(
                'SELECT * FROM contract_items WHERE id = ? AND contract_id = ?',
                (contract_item_id, contract_id),
            ).fetchone()
            if not baseline:
                raise ValueError('投产通知产品不存在或不属于当前合同')
            start_text = str(raw.get('serial_start') or '').strip()
            end_text = str(raw.get('serial_end') or '').strip()
            if bool(start_text) != bool(end_text):
                raise ValueError(f"{baseline['item_name']}的起止号必须同时填写")
            serial_start = serial_end = None
            if start_text:
                try:
                    serial_start, serial_end = int(start_text), int(end_text)
                except ValueError as exc:
                    raise ValueError(f"{baseline['item_name']}的号段必须是整数") from exc
                if serial_end < serial_start or serial_end - serial_start + 1 != qty:
                    raise ValueError(f"{baseline['item_name']}的号段长度必须等于投产数量")
                if baseline['serial_start'] is not None and serial_start < baseline['serial_start']:
                    raise ValueError(f"{baseline['item_name']}的起始号超出合同范围")
                if baseline['serial_end'] is not None and serial_end > baseline['serial_end']:
                    raise ValueError(f"{baseline['item_name']}的结束号超出合同范围")
            unit_price_minor = baseline['unit_price_minor']
            parsed.append({
                'contract_item_id': contract_item_id,
                'line_no': index,
                'item_name': baseline['item_name'],
                'spec_model': baseline['spec_model'] or '',
                'drawing_no': baseline['drawing_no'] or '',
                'unit': baseline['unit'] or '个',
                'notice_qty': qty,
                'unit_price_minor': unit_price_minor,
                'amount_minor': qty * unit_price_minor if unit_price_minor is not None else 0,
                'serial_start': serial_start,
                'serial_end': serial_end,
                'required_delivery_date': str(raw.get('required_delivery_date') or '').strip(),
                'remark': str(raw.get('remark') or '').strip(),
            })
        if not parsed:
            raise ValueError('投产通知至少需要一条产品明细')
        return parsed

    def _save_items_impl(self, conn, notice, rows):
        parsed = self._parse_item_rows(conn, notice['contract_id'], rows)
        now = self.now()
        conn.execute('DELETE FROM production_notice_items WHERE notice_id = ?', (notice['id'],))
        for item in parsed:
            conn.execute(
                """INSERT INTO production_notice_items (
                       notice_id, contract_item_id, line_no, item_name, spec_model,
                       drawing_no, unit, notice_qty, unit_price_minor, amount_minor,
                       serial_start, serial_end, required_delivery_date, remark,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    notice['id'], item['contract_item_id'], item['line_no'],
                    item['item_name'], item['spec_model'], item['drawing_no'], item['unit'],
                    item['notice_qty'], item['unit_price_minor'], item['amount_minor'],
                    item['serial_start'], item['serial_end'],
                    item['required_delivery_date'], item['remark'], now, now,
                ),
            )
        total_qty = sum(item['notice_qty'] for item in parsed)
        total_amount_minor = sum(item['amount_minor'] for item in parsed)
        conn.execute(
            'UPDATE production_notices SET total_qty = ?, total_amount_minor = ?, '
            'updated_at = ? WHERE id = ?',
            (total_qty, total_amount_minor, now, notice['id']),
        )

    def create(self, contract_id, header, rows):
        now = self.now()
        with self.get_conn() as conn:
            begin_immediate(conn)
            contract = active_contract(conn, contract_id)
            notice_no = str(header.get('notice_no') or '').strip() or self._next_notice_no(conn)
            cur = conn.execute(
                """INSERT INTO production_notices (
                       contract_id, notice_no, version, notice_date, status,
                       supplier_name, project_name, remark, created_at, updated_at
                   ) VALUES (?, ?, 1, ?, 'draft', ?, ?, ?, ?, ?)""",
                (
                    contract_id, notice_no, str(header.get('notice_date') or '').strip(),
                    str(header.get('supplier_name') or contract['counterparty'] or '').strip(),
                    str(header.get('project_name') or contract['project_name'] or '').strip(),
                    str(header.get('remark') or '').strip(), now, now,
                ),
            )
            notice_id = cur.lastrowid
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            self._save_items_impl(conn, notice, rows)
            self._history(conn, notice_id, 'create', '', 'draft', header.get('operator', ''))
        return notice_id

    def save_draft(self, notice_id, header, rows):
        with self.get_conn() as conn:
            begin_immediate(conn)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            if not notice:
                raise ValueError('投产通知不存在')
            if notice['status'] != 'draft':
                raise ValueError('只有草稿状态的投产通知可以编辑')
            active_contract(conn, notice['contract_id'])
            notice_no = str(header.get('notice_no') or '').strip()
            if not notice_no:
                raise ValueError('投产通知编号不能为空')
            cursor = conn.execute(
                """UPDATE production_notices
                   SET notice_no = ?, notice_date = ?, supplier_name = ?,
                       project_name = ?, remark = ?, updated_at = ?
                   WHERE id = ? AND status = 'draft'""",
                (
                    notice_no, str(header.get('notice_date') or '').strip(),
                    str(header.get('supplier_name') or '').strip(),
                    str(header.get('project_name') or '').strip(),
                    str(header.get('remark') or '').strip(), self.now(), notice_id,
                ),
            )
            require_conditional_update(cursor)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            self._save_items_impl(conn, notice, rows)
            self._history(conn, notice_id, 'edit', 'draft', 'draft', header.get('operator', ''))
        return notice_id

    @staticmethod
    def _validate_issue(conn, notice):
        items = conn.execute(
            """SELECT pni.*, ci.contracted_qty, ci.serial_start AS baseline_start,
                      ci.serial_end AS baseline_end
               FROM production_notice_items pni
               JOIN contract_items ci ON ci.id = pni.contract_item_id
               WHERE pni.notice_id = ? ORDER BY pni.line_no""",
            (notice['id'],),
        ).fetchall()
        if not items:
            raise ValueError('投产通知至少需要一条产品明细')
        if not notice['notice_date']:
            raise ValueError('正式发出前必须填写通知日期')
        for item in items:
            issued = conn.execute(
                """SELECT COALESCE(SUM(other.notice_qty), 0)
                   FROM production_notice_items other
                   JOIN production_notices pn ON pn.id = other.notice_id
                   WHERE other.contract_item_id = ?
                     AND other.notice_id NOT IN (?, ?)
                     AND pn.status IN ('issued','acknowledged','closed')""",
                (
                    item['contract_item_id'], notice['id'],
                    notice['supersedes_notice_id'] or -1,
                ),
            ).fetchone()[0]
            if issued + item['notice_qty'] > item['contracted_qty']:
                remaining = max(0, item['contracted_qty'] - issued)
                raise ValueError(
                    f"{item['item_name']}本次投产 {item['notice_qty']}，超过剩余可发数量 {remaining}"
                )
            if item['unit_price_minor'] is None:
                raise ValueError(f"{item['item_name']}缺少合同单价，不能正式发出")
            if item['serial_start'] is not None:
                overlap = conn.execute(
                    """SELECT pn.notice_no, pn.version
                       FROM production_notice_items other
                       JOIN production_notices pn ON pn.id = other.notice_id
                       WHERE other.contract_item_id = ?
                         AND other.notice_id NOT IN (?, ?)
                         AND pn.status IN ('issued','acknowledged','closed')
                         AND other.serial_start IS NOT NULL
                         AND NOT (other.serial_end < ? OR other.serial_start > ?)
                       LIMIT 1""",
                    (
                        item['contract_item_id'], notice['id'],
                        notice['supersedes_notice_id'] or -1,
                        item['serial_start'], item['serial_end'],
                    ),
                ).fetchone()
                if overlap:
                    raise ValueError(
                        f"{item['item_name']}号段与 {overlap['notice_no']} 第{overlap['version']}版重叠"
                    )
        return items

    def _cancel_impl(self, conn, notice, operator, reason, action='cancel'):
        ensure_event_has_no_payment(conn, notice['payment_trigger_event_id'])
        ensure_notice_has_no_invoice_allocations(conn, notice['id'])
        now = self.now()
        if notice['payment_trigger_event_id']:
            conn.execute(
                """UPDATE payment_plans
                   SET confirm_status = 'void', updated_at = ?
                   WHERE trigger_event_id = ? AND paid_amount_minor = 0""",
                (now, notice['payment_trigger_event_id']),
            )
            event = conn.execute(
                'SELECT metadata_json FROM payment_trigger_events WHERE id = ?',
                (notice['payment_trigger_event_id'],),
            ).fetchone()
            try:
                metadata = json.loads(event['metadata_json'] or '{}') if event else {}
            except (TypeError, ValueError):
                metadata = {}
            metadata.update({'cancelled': True, 'cancellation_reason': reason})
            conn.execute(
                'UPDATE payment_trigger_events SET metadata_json = ?, updated_at = ? WHERE id = ?',
                (json.dumps(metadata, ensure_ascii=False), now, notice['payment_trigger_event_id']),
            )
        cursor = conn.execute(
            """UPDATE production_notices
               SET status = 'cancelled', cancelled_at = ?, cancelled_by = ?,
                   cancellation_reason = ?, updated_at = ?
               WHERE id = ? AND status = ?""",
            (now, operator or '', reason, now, notice['id'], notice['status']),
        )
        require_conditional_update(cursor)
        self._history(
            conn, notice['id'], action, notice['status'], 'cancelled', operator, reason
        )

    def issue(self, notice_id, operator=''):
        with self.get_conn() as conn:
            begin_immediate(conn)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            if not notice:
                raise ValueError('投产通知不存在')
            if notice['status'] != 'draft':
                raise ValueError('只有草稿状态的投产通知可以正式发出')
            active_contract(conn, notice['contract_id'])
            other_active = conn.execute(
                """SELECT id, version FROM production_notices
                   WHERE contract_id = ? AND notice_no = ? AND id != ?
                     AND id != ?
                     AND status IN ('issued','acknowledged','closed')
                   ORDER BY version DESC LIMIT 1""",
                (
                    notice['contract_id'], notice['notice_no'], notice['id'],
                    notice['supersedes_notice_id'] or -1,
                ),
            ).fetchone()
            if other_active:
                raise ValueError(
                    f"该通知已有第{other_active['version']}版生效，请从当前生效版本创建修订"
                )
            self._validate_issue(conn, notice)
            if notice['supersedes_notice_id']:
                original = conn.execute(
                    'SELECT * FROM production_notices WHERE id = ?',
                    (notice['supersedes_notice_id'],),
                ).fetchone()
                if original and original['status'] in ACTIVE_NOTICE_STATUSES:
                    self._cancel_impl(
                        conn, original, operator,
                        f"已由 {notice['notice_no']} 第{notice['version']}版替代",
                        action='superseded',
                    )
            reference_no = (
                notice['notice_no'] if notice['version'] == 1
                else f"{notice['notice_no']}#v{notice['version']}"
            )
            event_id, plan_ids = self.payment_rules.create_matching_event_instances_impl(
                conn,
                contract_id=notice['contract_id'],
                event_type='production_notice_issued',
                reference_no=reference_no,
                event_date=notice['notice_date'],
                base_amount_minor=notice['total_amount_minor'],
                reference_name=f"投产通知 {notice['notice_no']} 第{notice['version']}版",
                metadata={
                    'production_notice_id': notice['id'],
                    'notice_no': notice['notice_no'],
                    'version': notice['version'],
                    'total_qty': notice['total_qty'],
                },
            )
            now = self.now()
            try:
                cursor = conn.execute(
                    """UPDATE production_notices
                       SET status = 'issued', issued_at = ?, issued_by = ?,
                           payment_trigger_event_id = ?, updated_at = ?
                       WHERE id = ? AND status = 'draft'""",
                    (now, operator or '', event_id, now, notice_id),
                )
                require_conditional_update(cursor)
            except sqlite3.IntegrityError as exc:
                if '只能有一个生效版本' in str(exc):
                    raise ValueError('同一投产通知只能有一个生效版本') from exc
                raise
            self._history(
                conn, notice_id, 'issue', 'draft', 'issued', operator,
                f'生成 {len(plan_ids)} 条动态付款实例',
            )
        return {'event_id': event_id, 'payment_plan_ids': plan_ids}

    def acknowledge(self, notice_id, operator=''):
        with self.get_conn() as conn:
            begin_immediate(conn)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            if not notice or notice['status'] != 'issued':
                raise ValueError('只有已发出的投产通知可以确认收悉')
            now = self.now()
            cursor = conn.execute(
                """UPDATE production_notices
                   SET status = 'acknowledged', acknowledged_at = ?,
                       acknowledged_by = ?, updated_at = ?
                   WHERE id = ? AND status = 'issued'""",
                (now, operator or '', now, notice_id),
            )
            require_conditional_update(cursor)
            self._history(conn, notice_id, 'acknowledge', 'issued', 'acknowledged', operator)

    def close(self, notice_id, operator=''):
        with self.get_conn() as conn:
            begin_immediate(conn)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            if not notice or notice['status'] not in {'issued', 'acknowledged'}:
                raise ValueError('只有已发出或已确认的投产通知可以关闭')
            now = self.now()
            cursor = conn.execute(
                """UPDATE production_notices SET status = 'closed', closed_at = ?,
                   updated_at = ? WHERE id = ? AND status = ?""",
                (now, now, notice_id, notice['status']),
            )
            require_conditional_update(cursor)
            self._history(conn, notice_id, 'close', notice['status'], 'closed', operator)

    def cancel(self, notice_id, operator='', reason=''):
        reason = str(reason or '').strip()
        if not reason:
            raise ValueError('取消投产通知必须填写原因')
        with self.get_conn() as conn:
            begin_immediate(conn)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            if not notice or notice['status'] == 'cancelled':
                raise ValueError('投产通知不存在或已取消')
            self._cancel_impl(conn, notice, operator, reason)

    def revise(self, notice_id, operator=''):
        now = self.now()
        with self.get_conn() as conn:
            begin_immediate(conn)
            notice = conn.execute(
                'SELECT * FROM production_notices WHERE id = ?', (notice_id,)
            ).fetchone()
            if not notice or notice['status'] not in ACTIVE_NOTICE_STATUSES:
                raise ValueError('只有生效中的投产通知可以创建修订版')
            active_contract(conn, notice['contract_id'])
            ensure_event_has_no_payment(conn, notice['payment_trigger_event_id'])
            ensure_notice_has_no_invoice_allocations(conn, notice['id'])
            existing_draft = conn.execute(
                """SELECT version FROM production_notices
                   WHERE contract_id = ? AND notice_no = ? AND status = 'draft'
                   ORDER BY version DESC LIMIT 1""",
                (notice['contract_id'], notice['notice_no']),
            ).fetchone()
            if existing_draft:
                raise ValueError(
                    f"该通知已有第{existing_draft['version']}版修订草稿，请先处理该草稿"
                )
            version = conn.execute(
                """SELECT COALESCE(MAX(version), 0) + 1 FROM production_notices
                   WHERE contract_id = ? AND notice_no = ?""",
                (notice['contract_id'], notice['notice_no']),
            ).fetchone()[0]
            cur = conn.execute(
                """INSERT INTO production_notices (
                       contract_id, notice_no, version, notice_date, status,
                       supplier_name, project_name, supersedes_notice_id,
                       total_qty, total_amount_minor, remark, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    notice['contract_id'], notice['notice_no'], version,
                    notice['notice_date'], notice['supplier_name'], notice['project_name'],
                    notice['id'], notice['total_qty'], notice['total_amount_minor'],
                    notice['remark'], now, now,
                ),
            )
            new_id = cur.lastrowid
            conn.execute(
                """INSERT INTO production_notice_items (
                       notice_id, contract_item_id, line_no, item_name, spec_model,
                       drawing_no, unit, notice_qty, unit_price_minor, amount_minor,
                       serial_start, serial_end, required_delivery_date, remark,
                       created_at, updated_at
                   ) SELECT ?, contract_item_id, line_no, item_name, spec_model,
                            drawing_no, unit, notice_qty, unit_price_minor, amount_minor,
                            serial_start, serial_end, required_delivery_date, remark, ?, ?
                     FROM production_notice_items WHERE notice_id = ?""",
                (new_id, now, now, notice_id),
            )
            self._history(
                conn, new_id, 'revise_create', '', 'draft', operator,
                f"从第{notice['version']}版创建",
            )
        return new_id
