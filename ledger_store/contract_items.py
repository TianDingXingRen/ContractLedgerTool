"""Contract product baselines used by production notices."""

from __future__ import annotations

import json
from contextlib import nullcontext

from . import money_fields


_QUANTITY_UNITS = frozenset({'个', '件', '套', '台', '支', '只', '组', '批'})


def parse_contracted_qty(value):
    """Return a positive whole-number quantity or raise a user-facing error."""
    if isinstance(value, bool):
        raise ValueError('合同数量必须是正整数')
    text = str(value or '').strip()
    number_text = text
    if number_text[-1:] in _QUANTITY_UNITS:
        number_text = number_text[:-1].strip()
    whole, separator, fraction = number_text.partition('.')
    valid_decimal = not separator or (fraction and not fraction.strip('0'))
    if not whole.isdigit() or not valid_decimal:
        raise ValueError(f'合同数量“{text or "空"}”不是正整数，请人工确认')
    quantity = int(whole)
    if quantity <= 0:
        raise ValueError(f'合同数量“{text or "空"}”不是正整数，请人工确认')
    return quantity


class ContractItemRepository:
    def __init__(self, *, get_conn, now):
        self.get_conn = get_conn
        self.now = now

    @staticmethod
    def _public(row):
        if row is None:
            return None
        item = dict(row)
        for public, minor in (
            ('unit_price', 'unit_price_minor'),
            ('amount', 'amount_minor'),
        ):
            item[public] = None if item.get(minor) is None else item[minor] / 100
        item['issued_qty'] = int(item.get('issued_qty') or 0)
        item['remaining_qty'] = int(item.get('contracted_qty') or 0) - item['issued_qty']
        return item

    def list(self, contract_id):
        with self.get_conn() as conn:
            rows = conn.execute(
                """
                SELECT ci.*,
                       COALESCE(SUM(CASE WHEN pn.status IN ('issued','acknowledged','closed')
                                         THEN pni.notice_qty ELSE 0 END), 0) AS issued_qty
                FROM contract_items ci
                LEFT JOIN production_notice_items pni ON pni.contract_item_id = ci.id
                LEFT JOIN production_notices pn ON pn.id = pni.notice_id
                WHERE ci.contract_id = ?
                GROUP BY ci.id
                ORDER BY ci.line_no, ci.id
                """,
                (contract_id,),
            ).fetchall()
        return [self._public(row) for row in rows]

    def get(self, item_id, contract_id=None):
        sql = """
            SELECT ci.*,
                   COALESCE(SUM(CASE WHEN pn.status IN ('issued','acknowledged','closed')
                                     THEN pni.notice_qty ELSE 0 END), 0) AS issued_qty
            FROM contract_items ci
            LEFT JOIN production_notice_items pni ON pni.contract_item_id = ci.id
            LEFT JOIN production_notices pn ON pn.id = pni.notice_id
            WHERE ci.id = ?
        """
        params = [item_id]
        if contract_id is not None:
            sql += ' AND ci.contract_id = ?'
            params.append(contract_id)
        sql += ' GROUP BY ci.id'
        with self.get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._public(row)

    def _history(self, conn, contract_id, item_id, action, *, before=None, after=None,
                 operator='', note=''):
        conn.execute(
            """INSERT INTO contract_item_history (
                   contract_id, item_id, action, operator, before_json,
                   after_json, note, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contract_id, item_id, action, str(operator or '').strip(),
                json.dumps(dict(before) if before else {}, ensure_ascii=False),
                json.dumps(dict(after) if after else {}, ensure_ascii=False),
                str(note or '').strip(), self.now(),
            ),
        )

    def history(self, contract_id):
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM contract_item_history
                   WHERE contract_id = ? ORDER BY created_at DESC, id DESC""",
                (contract_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for key in ('before_json', 'after_json'):
                try:
                    item[key.removesuffix('_json')] = json.loads(item.get(key) or '{}')
                except (TypeError, ValueError):
                    item[key.removesuffix('_json')] = {}
            result.append(item)
        return result

    @staticmethod
    def _item_id(raw):
        try:
            return int(raw.get('id') or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError('合同产品 ID 无效') from exc

    def _validate_existing_names(self, rows):
        """Require explicit deletion before any temporary line renumbering."""
        for raw in rows:
            item_id = self._item_id(raw)
            if (
                item_id
                and not raw.get('delete')
                and not str(raw.get('item_name') or '').strip()
            ):
                raise ValueError('合同产品名称不能为空；如需删除请勾选删除')

    def _validate_unique_item_ids(self, rows):
        """Reject a stale or forged form that submits one stored row twice."""
        submitted_ids = set()
        for raw in rows:
            item_id = self._item_id(raw)
            if not item_id:
                continue
            if item_id in submitted_ids:
                raise ValueError('合同产品 ID 不能重复提交')
            submitted_ids.add(item_id)

    def _free_submitted_line_numbers(self, conn, contract_id, rows):
        submitted_ids = [
            item_id
            for raw in rows
            if (item_id := self._item_id(raw))
        ]
        originals = {}
        for offset, item_id in enumerate(dict.fromkeys(submitted_ids), start=1):
            current = conn.execute(
                'SELECT * FROM contract_items WHERE id = ? AND contract_id = ?',
                (item_id, contract_id),
            ).fetchone()
            if not current:
                raise ValueError('合同产品不存在或不属于当前合同')
            originals[item_id] = current
            conn.execute(
                'UPDATE contract_items SET line_no = ? WHERE id = ?',
                (-offset, item_id),
            )
        return originals

    def save(self, contract_id, rows, *, operator=''):
        rows = list(rows or [])
        now = self.now()
        saved = []
        with self.get_conn() as conn:
            contract = conn.execute(
                """SELECT id FROM contracts
                   WHERE id = ? AND (deleted_at = '' OR deleted_at IS NULL)""",
                (contract_id,),
            ).fetchone()
            if not contract:
                raise ValueError('合同不存在、已删除或不可编辑')
            self._validate_unique_item_ids(rows)
            self._validate_existing_names(rows)
            originals = self._free_submitted_line_numbers(
                conn, contract_id, rows
            )
            existing_lines = {}
            for index, raw in enumerate(rows, start=1):
                if raw.get('delete'):
                    item_id = self._item_id(raw)
                    if not item_id:
                        continue
                    used = conn.execute(
                        'SELECT 1 FROM production_notice_items WHERE contract_item_id = ? LIMIT 1',
                        (item_id,),
                    ).fetchone()
                    if used:
                        raise ValueError('已被投产通知引用的合同产品不能删除')
                    before = originals.get(item_id)
                    conn.execute(
                        'DELETE FROM contract_items WHERE id = ? AND contract_id = ?',
                        (item_id, contract_id),
                    )
                    if before:
                        self._history(
                            conn, contract_id, item_id, 'delete', before=before,
                            operator=operator,
                        )
                    continue
                item_name = str(raw.get('item_name') or '').strip()
                if not item_name:
                    continue
                line_no = int(raw.get('line_no') or index)
                if line_no <= 0 or line_no in existing_lines:
                    raise ValueError('合同产品行号必须是互不重复的正整数')
                existing_lines[line_no] = True
                qty = parse_contracted_qty(raw.get('contracted_qty'))
                unit_price_minor, _ = money_fields.amount_pair(raw.get('unit_price'))
                if unit_price_minor is not None and unit_price_minor < 0:
                    raise ValueError('合同产品单价不能小于 0')
                amount_minor = qty * unit_price_minor if unit_price_minor is not None else None
                start_text = str(raw.get('serial_start') or '').strip()
                end_text = str(raw.get('serial_end') or '').strip()
                if bool(start_text) != bool(end_text):
                    raise ValueError(f'{item_name}的合同起止号必须同时填写')
                serial_start = serial_end = None
                if start_text:
                    try:
                        serial_start, serial_end = int(start_text), int(end_text)
                    except ValueError as exc:
                        raise ValueError(f'{item_name}的合同号段必须是整数') from exc
                    if serial_end < serial_start or serial_end - serial_start + 1 != qty:
                        raise ValueError(f'{item_name}的合同号段长度必须等于合同数量')
                item_id = self._item_id(raw)
                if item_id:
                    current = conn.execute(
                        'SELECT * FROM contract_items WHERE id = ? AND contract_id = ?',
                        (item_id, contract_id),
                    ).fetchone()
                    if not current:
                        raise ValueError('合同产品不存在或不属于当前合同')
                    issued = conn.execute(
                        """SELECT COALESCE(SUM(pni.notice_qty), 0)
                           FROM production_notice_items pni
                           JOIN production_notices pn ON pn.id = pni.notice_id
                           WHERE pni.contract_item_id = ?
                             AND pn.status IN ('issued','acknowledged','closed')""",
                        (item_id,),
                    ).fetchone()[0]
                    if qty < issued:
                        raise ValueError(f'{item_name}的合同数量不能小于累计已发数量 {issued}')
                    conn.execute(
                        """
                        UPDATE contract_items
                        SET line_no = ?, item_code = ?, item_name = ?, spec_model = ?,
                            drawing_no = ?, quantity_text = ?, contracted_qty = ?, unit = ?,
                            unit_price_minor = ?, amount_minor = ?, serial_start = ?,
                            serial_end = ?, updated_at = ?
                        WHERE id = ? AND contract_id = ?
                        """,
                        (
                            line_no, str(raw.get('item_code') or '').strip(), item_name,
                            str(raw.get('spec_model') or '').strip(),
                            str(raw.get('drawing_no') or '').strip(), str(qty), qty,
                            str(raw.get('unit') or '个').strip() or '个',
                            unit_price_minor, amount_minor, serial_start, serial_end,
                            now, item_id, contract_id,
                        ),
                    )
                    after = conn.execute(
                        'SELECT * FROM contract_items WHERE id = ?', (item_id,)
                    ).fetchone()
                    self._history(
                        conn, contract_id, item_id, 'update',
                        before=originals.get(item_id, current),
                        after=after, operator=operator,
                    )
                    saved.append(item_id)
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO contract_items (
                            contract_id, source_type, line_no, item_code, item_name,
                            spec_model, drawing_no, quantity_text, contracted_qty, unit,
                            unit_price_minor, amount_minor, serial_start, serial_end,
                            created_at, updated_at
                        ) VALUES (?, 'manual', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            contract_id, line_no, str(raw.get('item_code') or '').strip(),
                            item_name, str(raw.get('spec_model') or '').strip(),
                            str(raw.get('drawing_no') or '').strip(), str(qty), qty,
                            str(raw.get('unit') or '个').strip() or '个',
                            unit_price_minor, amount_minor, serial_start, serial_end,
                            now, now,
                        ),
                    )
                    after = conn.execute(
                        'SELECT * FROM contract_items WHERE id = ?', (cur.lastrowid,)
                    ).fetchone()
                    self._history(
                        conn, contract_id, cur.lastrowid, 'create', after=after,
                        operator=operator,
                    )
                    saved.append(cur.lastrowid)
        return saved

    def sync_from_procurement(self, contract_id, *, connection=None, strict=True):
        """Import awarded lines once, preserving later manual baseline edits."""
        now = self.now()
        report = {'created': 0, 'updated': 0, 'skipped': 0, 'issues': []}
        manager = nullcontext(connection) if connection is not None else self.get_conn()
        with manager as conn:
            rows = conn.execute(
                """
                SELECT ai.*
                FROM project_contract_links l
                JOIN award_recommendation_items ai
                  ON ai.recommendation_id = l.recommendation_id
                WHERE l.contract_id = ?
                ORDER BY ai.id
                """,
                (contract_id,),
            ).fetchall()
            if not rows:
                if strict:
                    raise ValueError('当前合同没有可同步的定标产品明细')
                report['issues'].append('当前合同没有可同步的定标产品明细')
                conn.execute(
                    """INSERT INTO contract_history (
                           contract_id, field, old_value, new_value, changed_at
                       ) VALUES (?, 'contract_items_sync_issues', '', ?, ?)""",
                    (contract_id, json.dumps(report['issues'], ensure_ascii=False), now),
                )
                return report
            next_line = conn.execute(
                'SELECT COALESCE(MAX(line_no), 0) + 1 FROM contract_items WHERE contract_id = ?',
                (contract_id,),
            ).fetchone()[0]
            for row in rows:
                try:
                    qty = parse_contracted_qty(row['quantity_text'])
                except ValueError as exc:
                    report['skipped'] += 1
                    report['issues'].append(f"{row['item_name']}：{exc}")
                    continue
                existing = conn.execute(
                    """SELECT * FROM contract_items
                       WHERE contract_id = ? AND source_type = 'procurement_award'
                         AND source_id = ?""",
                    (contract_id, row['id']),
                ).fetchone()
                amount_minor = int(row['amount_minor'] or 0)
                unit_price_minor = int(row['unit_price_minor'] or 0)
                if existing:
                    used = conn.execute(
                        'SELECT 1 FROM production_notice_items WHERE contract_item_id = ? LIMIT 1',
                        (existing['id'],),
                    ).fetchone()
                    if used:
                        report['skipped'] += 1
                        continue
                    conn.execute(
                        """UPDATE contract_items
                           SET item_name = ?, spec_model = ?, quantity_text = ?,
                               contracted_qty = ?, unit = ?, unit_price_minor = ?,
                               amount_minor = ?, updated_at = ? WHERE id = ?""",
                        (
                            row['item_name'], row['spec_model'] or '', row['quantity_text'],
                            qty, row['unit'] or '个', unit_price_minor, amount_minor,
                            now, existing['id'],
                        ),
                    )
                    after = conn.execute(
                        'SELECT * FROM contract_items WHERE id = ?', (existing['id'],)
                    ).fetchone()
                    self._history(
                        conn, contract_id, existing['id'], 'procurement_sync_update',
                        before=existing, after=after, operator='system',
                    )
                    report['updated'] += 1
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO contract_items (
                        contract_id, source_type, source_id, line_no, item_name,
                        spec_model, quantity_text, contracted_qty, unit,
                        unit_price_minor, amount_minor, created_at, updated_at
                    ) VALUES (?, 'procurement_award', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract_id, row['id'], next_line, row['item_name'],
                        row['spec_model'] or '', row['quantity_text'], qty, row['unit'] or '个',
                        unit_price_minor, amount_minor, now, now,
                    ),
                )
                after = conn.execute(
                    'SELECT * FROM contract_items WHERE id = ?', (cur.lastrowid,)
                ).fetchone()
                self._history(
                    conn, contract_id, cur.lastrowid, 'procurement_sync_create',
                    after=after, operator='system',
                )
                next_line += 1
                report['created'] += 1
            if report['issues']:
                conn.execute(
                    """INSERT INTO contract_history (
                           contract_id, field, old_value, new_value, changed_at
                       ) VALUES (?, 'contract_items_sync_issues', '', ?, ?)""",
                    (
                        contract_id,
                        json.dumps(report['issues'], ensure_ascii=False),
                        now,
                    ),
                )
        return report
