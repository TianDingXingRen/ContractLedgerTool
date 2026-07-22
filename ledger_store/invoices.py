"""Incoming invoice ledger and allocation reconciliation."""

from __future__ import annotations

import json
import sqlite3

from . import money_fields


INVOICE_TYPES = {'vat_special', 'vat_normal', 'electronic', 'other'}
INVOICE_STATUSES = {'valid', 'red', 'void'}
REVIEW_STATUSES = {'pending', 'verified', 'exception'}
DEDUCTION_STATUSES = {'not_applicable', 'pending', 'deducted'}


class InvoiceRepository:
    def __init__(self, *, get_conn, now):
        self.get_conn = get_conn
        self.now = now

    @staticmethod
    def _public(row):
        if row is None:
            return None
        result = dict(row)
        for public, minor in (
            ('amount_ex_tax', 'amount_ex_tax_minor'),
            ('tax_amount', 'tax_amount_minor'),
            ('total_amount', 'total_amount_minor'),
            ('allocated_amount', 'allocated_amount_minor'),
        ):
            if minor in result:
                result[public] = (result.get(minor) or 0) / 100
        if 'tax_rate_bps' in result:
            result['tax_rate'] = (
                None if result.get('tax_rate_bps') is None
                else result['tax_rate_bps'] / 100
            )
        total = int(result.get('total_amount_minor') or 0)
        allocated = int(result.get('allocated_amount_minor') or 0)
        result['unallocated_amount_minor'] = total - allocated
        result['unallocated_amount'] = (total - allocated) / 100
        result['allocation_status'] = (
            'unallocated' if allocated == 0
            else 'allocated' if allocated == total
            else 'partial' if allocated < total
            else 'over'
        )
        return result

    def list(
        self, contract_id=None, review_status='', invoice_status='', page=0,
        per_page=50,
    ):
        conditions = []
        params = []
        if contract_id is not None:
            conditions.append(
                'EXISTS (SELECT 1 FROM invoice_allocations link '
                'WHERE link.invoice_id = i.id AND link.contract_id = ?)'
            )
            params.append(contract_id)
        if review_status:
            conditions.append('i.review_status = ?')
            params.append(review_status)
        if invoice_status:
            conditions.append('i.invoice_status = ?')
            params.append(invoice_status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        sql = f"""
                SELECT i.*,
                       COALESCE((SELECT SUM(ia.allocated_amount_minor)
                                 FROM invoice_allocations ia
                                 WHERE ia.invoice_id = i.id), 0) AS allocated_amount_minor,
                       (SELECT COUNT(*) FROM invoice_files f WHERE f.invoice_id = i.id)
                           AS file_count,
                       EXISTS(SELECT 1 FROM invoices red
                              WHERE red.original_invoice_id = i.id
                                AND red.invoice_status = 'red') AS has_red_offset
                FROM invoices i
                {where}
                ORDER BY i.issue_date DESC, i.id DESC
                """
        query_params = list(params)
        total = None
        if page > 0:
            with self.get_conn() as conn:
                total = conn.execute(
                    f'SELECT COUNT(*) FROM invoices i {where}', params
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

    def get(self, invoice_id):
        with self.get_conn() as conn:
            row = conn.execute(
                """SELECT i.*,
                          COALESCE((SELECT SUM(ia.allocated_amount_minor)
                                    FROM invoice_allocations ia
                                    WHERE ia.invoice_id = i.id), 0)
                              AS allocated_amount_minor,
                          EXISTS(SELECT 1 FROM invoices red
                                 WHERE red.original_invoice_id = i.id
                                   AND red.invoice_status = 'red') AS has_red_offset
                   FROM invoices i WHERE i.id = ?""",
                (invoice_id,),
            ).fetchone()
            if not row:
                return None
            allocations = conn.execute(
                """SELECT ia.*, c.contract_no, c.title AS contract_title,
                          pn.notice_no, pn.version AS notice_version,
                          pp.phase_name AS payment_phase
                   FROM invoice_allocations ia
                   JOIN contracts c ON c.id = ia.contract_id
                   LEFT JOIN production_notices pn ON pn.id = ia.production_notice_id
                   LEFT JOIN payment_plans pp ON pp.id = ia.payment_plan_id
                   WHERE ia.invoice_id = ? ORDER BY ia.id""",
                (invoice_id,),
            ).fetchall()
            files = conn.execute(
                'SELECT * FROM invoice_files WHERE invoice_id = ? ORDER BY id',
                (invoice_id,),
            ).fetchall()
            history = conn.execute(
                'SELECT * FROM invoice_history WHERE invoice_id = ? '
                'ORDER BY created_at DESC, id DESC',
                (invoice_id,),
            ).fetchall()
        result = self._public(row)
        result['allocations'] = [self._public(item) for item in allocations]
        result['files'] = [dict(item) for item in files]
        result['history'] = [dict(item) for item in history]
        return result

    def _snapshot(self, conn, invoice_id):
        invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
        allocations = conn.execute(
            'SELECT * FROM invoice_allocations WHERE invoice_id = ? ORDER BY id',
            (invoice_id,),
        ).fetchall()
        return json.dumps(
            {
                'invoice': dict(invoice) if invoice else {},
                'allocations': [dict(row) for row in allocations],
            },
            ensure_ascii=False,
        )

    def _history(self, conn, invoice_id, action, operator='', note=''):
        conn.execute(
            """INSERT INTO invoice_history (
                   invoice_id, action, operator, note, snapshot_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                invoice_id, action, operator or '', note or '',
                self._snapshot(conn, invoice_id), self.now(),
            ),
        )

    @staticmethod
    def _validated_money(data):
        values = {}
        for key in ('amount_ex_tax', 'tax_amount', 'total_amount'):
            minor, _ = money_fields.amount_pair(data.get(key), allow_none=False)
            if minor < 0:
                raise ValueError('发票金额不能小于 0')
            values[f'{key}_minor'] = minor
        if abs(
            values['amount_ex_tax_minor'] + values['tax_amount_minor']
            - values['total_amount_minor']
        ) > 1:
            raise ValueError('价税合计必须等于不含税金额加税额')
        if values['total_amount_minor'] <= 0:
            raise ValueError('发票价税合计必须大于 0')
        return values

    @staticmethod
    def _replace_allocations(
        conn, invoice_id, total_minor, allocations, now, *, invoice_status='valid'
    ):
        parsed = []
        allocated_total = 0
        notice_totals = {}
        plan_totals = {}
        for raw in allocations or []:
            contract_id = int(raw.get('contract_id') or 0)
            amount_minor, _ = money_fields.amount_pair(raw.get('allocated_amount'))
            if not contract_id and amount_minor is None:
                continue
            if not contract_id:
                raise ValueError('发票分摊必须选择合同')
            if amount_minor is None or amount_minor <= 0:
                raise ValueError('发票分摊金额必须大于 0')
            contract = conn.execute(
                'SELECT id FROM contracts WHERE id = ? AND deleted_at = ?',
                (contract_id, ''),
            ).fetchone()
            if not contract:
                raise ValueError('发票分摊所选合同不存在')
            notice_id = int(raw.get('production_notice_id') or 0) or None
            payment_plan_id = int(raw.get('payment_plan_id') or 0) or None
            if notice_id:
                notice = conn.execute(
                    """SELECT contract_id, status, total_amount_minor,
                              payment_trigger_event_id
                       FROM production_notices WHERE id = ?""",
                    (notice_id,),
                ).fetchone()
                if not notice or notice['contract_id'] != contract_id:
                    raise ValueError('所选投产通知不属于分摊合同')
                if notice['status'] not in {'issued', 'acknowledged', 'closed'}:
                    raise ValueError('发票只能分摊到已正式发出的投产通知')
                notice_totals[notice_id] = (
                    notice_totals.get(notice_id, 0) + amount_minor
                )
            if payment_plan_id:
                plan = conn.execute(
                    """SELECT contract_id, confirm_status, trigger_event_id,
                              due_amount_minor
                       FROM payment_plans WHERE id = ?""",
                    (payment_plan_id,),
                ).fetchone()
                if not plan or plan['contract_id'] != contract_id:
                    raise ValueError('所选付款计划不属于分摊合同')
                if plan['confirm_status'] == 'void':
                    raise ValueError('不能把发票分摊到已作废的付款计划')
                if plan['due_amount_minor'] is None:
                    raise ValueError('所选付款计划缺少应付金额，不能核销发票')
                plan_totals[payment_plan_id] = (
                    plan_totals.get(payment_plan_id, 0) + amount_minor
                )
            if notice_id and payment_plan_id and (
                plan['trigger_event_id'] != notice['payment_trigger_event_id']
            ):
                raise ValueError('所选付款计划不是由该投产通知生成的')
            allocated_total += amount_minor
            parsed.append((
                contract_id, notice_id, payment_plan_id, amount_minor,
                str(raw.get('remark') or '').strip(),
            ))
        if allocated_total > total_minor:
            raise ValueError('发票分摊合计不能超过价税合计')
        if invoice_status != 'valid' and parsed:
            raise ValueError('红字或作废发票不能保留业务分摊')
        effective_invoice = (
            "i.invoice_status = 'valid' AND NOT EXISTS ("
            "SELECT 1 FROM invoices red WHERE red.original_invoice_id = i.id "
            "AND red.invoice_status = 'red')"
        )
        for notice_id, new_amount in notice_totals.items():
            notice = conn.execute(
                'SELECT total_amount_minor FROM production_notices WHERE id = ?',
                (notice_id,),
            ).fetchone()
            existing_amount = conn.execute(
                f"""SELECT COALESCE(SUM(ia.allocated_amount_minor), 0)
                    FROM invoice_allocations ia
                    JOIN invoices i ON i.id = ia.invoice_id
                    WHERE ia.production_notice_id = ? AND ia.invoice_id != ?
                      AND {effective_invoice}""",
                (notice_id, invoice_id),
            ).fetchone()[0]
            if existing_amount + new_amount > notice['total_amount_minor']:
                raise ValueError('投产通知的累计发票分摊不能超过通知金额')
        for payment_plan_id, new_amount in plan_totals.items():
            plan = conn.execute(
                'SELECT due_amount_minor FROM payment_plans WHERE id = ?',
                (payment_plan_id,),
            ).fetchone()
            existing_amount = conn.execute(
                f"""SELECT COALESCE(SUM(ia.allocated_amount_minor), 0)
                    FROM invoice_allocations ia
                    JOIN invoices i ON i.id = ia.invoice_id
                    WHERE ia.payment_plan_id = ? AND ia.invoice_id != ?
                      AND {effective_invoice}""",
                (payment_plan_id, invoice_id),
            ).fetchone()[0]
            if existing_amount + new_amount > plan['due_amount_minor']:
                raise ValueError('付款计划的累计发票分摊不能超过应付金额')
        conn.execute('DELETE FROM invoice_allocations WHERE invoice_id = ?', (invoice_id,))
        for contract_id, notice_id, payment_plan_id, amount_minor, remark in parsed:
            conn.execute(
                """INSERT INTO invoice_allocations (
                       invoice_id, contract_id, production_notice_id, payment_plan_id,
                       allocated_amount_minor, remark, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id, contract_id, notice_id, payment_plan_id,
                    amount_minor, remark, now, now,
                ),
            )
        return allocated_total

    def save(self, data, allocations, invoice_id=None):
        invoice_no = str(data.get('invoice_no') or '').strip()
        if not invoice_no:
            raise ValueError('发票号码不能为空')
        invoice_type = str(data.get('invoice_type') or 'vat_special').strip()
        invoice_status = str(data.get('invoice_status') or 'valid').strip()
        review_status = str(data.get('review_status') or 'pending').strip()
        deduction_status = str(data.get('deduction_status') or 'not_applicable').strip()
        if invoice_type not in INVOICE_TYPES:
            raise ValueError('发票类型无效')
        if invoice_status not in INVOICE_STATUSES:
            raise ValueError('发票状态无效')
        if review_status not in REVIEW_STATUSES:
            raise ValueError('核验状态无效')
        if deduction_status not in DEDUCTION_STATUSES:
            raise ValueError('抵扣状态无效')
        if invoice_status == 'void' and review_status == 'verified':
            raise ValueError('作废发票不能标记为已核验')
        if deduction_status == 'deducted' and (
            invoice_status != 'valid' or review_status != 'verified'
        ):
            raise ValueError('只有有效且已核验的发票才能标记为已抵扣')
        amounts = self._validated_money(data)
        tax_rate = data.get('tax_rate')
        tax_rate_bps = None if tax_rate in (None, '') else int(round(float(tax_rate) * 100))
        if tax_rate_bps is not None and not 0 <= tax_rate_bps <= 10000:
            raise ValueError('税率必须在 0% 到 100% 之间')
        original_invoice_id = int(data.get('original_invoice_id') or 0) or None
        if invoice_status == 'red' and not original_invoice_id:
            raise ValueError('红字发票必须关联原发票')
        if invoice_status != 'red' and original_invoice_id:
            raise ValueError('只有红字发票可以关联原发票')
        if invoice_id and original_invoice_id == invoice_id:
            raise ValueError('红字发票不能关联自身')
        now = self.now()
        try:
            with self.get_conn() as conn:
                if original_invoice_id:
                    original = conn.execute(
                        """SELECT id, invoice_status, total_amount_minor
                           FROM invoices WHERE id = ?""",
                        (original_invoice_id,),
                    ).fetchone()
                    if not original:
                        raise ValueError('关联的原发票不存在')
                    if original['invoice_status'] != 'valid':
                        raise ValueError('红字发票只能关联有效的原发票')
                    if original['total_amount_minor'] != amounts['total_amount_minor']:
                        raise ValueError('当前仅支持全额红冲，红字金额必须等于原发票金额')
                    other_red = conn.execute(
                        """SELECT 1 FROM invoices
                           WHERE original_invoice_id = ? AND invoice_status = 'red'
                             AND id != ? LIMIT 1""",
                        (original_invoice_id, invoice_id or -1),
                    ).fetchone()
                    if other_red:
                        raise ValueError('该原发票已经存在有效红字发票')
                params = (
                    str(data.get('invoice_code') or '').strip(), invoice_no, invoice_type,
                    str(data.get('issue_date') or '').strip(),
                    str(data.get('received_date') or '').strip(),
                    str(data.get('seller_name') or '').strip(),
                    str(data.get('seller_tax_no') or '').strip().upper(),
                    str(data.get('buyer_name') or '').strip(),
                    str(data.get('buyer_tax_no') or '').strip().upper(),
                    str(data.get('currency') or 'CNY').strip().upper() or 'CNY',
                    amounts['amount_ex_tax_minor'], amounts['tax_amount_minor'],
                    amounts['total_amount_minor'], tax_rate_bps, invoice_status,
                    review_status, deduction_status, original_invoice_id,
                    str(data.get('remark') or '').strip(),
                )
                if invoice_id:
                    if not conn.execute(
                        'SELECT 1 FROM invoices WHERE id = ?', (invoice_id,)
                    ).fetchone():
                        raise ValueError('发票不存在')
                    conn.execute(
                        """UPDATE invoices SET
                               invoice_code = ?, invoice_no = ?, invoice_type = ?,
                               issue_date = ?, received_date = ?, seller_name = ?,
                               seller_tax_no = ?, buyer_name = ?, buyer_tax_no = ?,
                               currency = ?, amount_ex_tax_minor = ?, tax_amount_minor = ?,
                               total_amount_minor = ?, tax_rate_bps = ?, invoice_status = ?,
                               review_status = ?, deduction_status = ?, original_invoice_id = ?,
                               remark = ?, updated_at = ? WHERE id = ?""",
                        (*params, now, invoice_id),
                    )
                    action = 'edit'
                else:
                    cur = conn.execute(
                        """INSERT INTO invoices (
                               invoice_code, invoice_no, invoice_type, issue_date,
                               received_date, seller_name, seller_tax_no, buyer_name,
                               buyer_tax_no, currency, amount_ex_tax_minor,
                               tax_amount_minor, total_amount_minor, tax_rate_bps,
                               invoice_status, review_status, deduction_status,
                               original_invoice_id, remark, created_at, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (*params, now, now),
                    )
                    invoice_id = cur.lastrowid
                    action = 'create'
                allocated = self._replace_allocations(
                    conn, invoice_id, amounts['total_amount_minor'], allocations, now,
                    invoice_status=invoice_status,
                )
                if (
                    invoice_status == 'valid'
                    and review_status == 'verified'
                    and allocated != amounts['total_amount_minor']
                ):
                    raise ValueError('有效发票必须全额分摊后才能核验通过')
                self._history(conn, invoice_id, action, data.get('operator', ''))
        except sqlite3.IntegrityError as exc:
            if 'idx_invoices_business_unique' in str(exc) or 'unique constraint' in str(exc).lower():
                raise ValueError('该销方、发票代码和发票号码已存在') from exc
            raise
        return invoice_id

    def add_file(self, invoice_id, *, original_filename, storage_path, content_type='', file_size=0, sha256=''):
        with self.get_conn() as conn:
            if not conn.execute('SELECT 1 FROM invoices WHERE id = ?', (invoice_id,)).fetchone():
                raise ValueError('发票不存在')
            try:
                cur = conn.execute(
                    """INSERT INTO invoice_files (
                           invoice_id, original_filename, storage_path, content_type,
                           file_size, sha256, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        invoice_id, original_filename, storage_path, content_type or '',
                        int(file_size or 0), sha256 or '', self.now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError('该附件已经上传') from exc
            self._history(conn, invoice_id, 'file_add', note=original_filename)
            return cur.lastrowid

    def get_file(self, file_id, invoice_id=None):
        sql = 'SELECT * FROM invoice_files WHERE id = ?'
        params = [file_id]
        if invoice_id is not None:
            sql += ' AND invoice_id = ?'
            params.append(invoice_id)
        with self.get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def delete_file(self, file_id, invoice_id):
        with self.get_conn() as conn:
            row = conn.execute(
                'SELECT * FROM invoice_files WHERE id = ? AND invoice_id = ?',
                (file_id, invoice_id),
            ).fetchone()
            if not row:
                return None
            conn.execute('DELETE FROM invoice_files WHERE id = ?', (file_id,))
            self._history(conn, invoice_id, 'file_delete', note=row['original_filename'])
            return dict(row)
