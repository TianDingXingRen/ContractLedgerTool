"""Historical awarded-price search and target-price assistance."""

from __future__ import annotations

from decimal import Decimal
from statistics import median

import ledger_store


def search_prices(q='', limit=200):
    clauses = ["a.status IN ('confirmed','converted')"]
    params = []
    if q:
        token = f'%{q}%'
        clauses.append('(ai.item_name LIKE ? OR ai.spec_model LIKE ? OR pi.drawing_no LIKE ? OR p.project_name LIKE ?)')
        params.extend([token, token, token, token])
    with ledger_store.get_conn() as conn:
        rows = conn.execute(
            f"""SELECT ai.*, p.project_no, p.project_name, p.purchase_method,
                       COALESCE(s.supplier_name, a.supplier_summary) supplier_name,
                       pi.drawing_no, a.created_at award_date, a.status award_status,
                       l.contract_id
                FROM award_recommendation_items ai
                JOIN award_recommendations a ON a.id = ai.recommendation_id
                JOIN procurement_projects p ON p.id = a.project_id
                LEFT JOIN project_items pi ON pi.id = ai.project_item_id
                LEFT JOIN project_suppliers s ON s.id = ai.supplier_id
                LEFT JOIN project_contract_links l ON l.recommendation_id = a.id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.created_at DESC, ai.id DESC LIMIT ?""",
            (*params, min(1000, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def price_assistance(q):
    rows = search_prices(q=q, limit=500)
    prices = [int(row['unit_price_minor']) for row in rows if row['unit_price_minor'] is not None]
    if not prices:
        return {'rows': rows, 'count': 0, 'min_minor': None, 'max_minor': None,
                'median_minor': None, 'suggested_target_minor': None}
    median_value = int(median(prices))
    suggested = int((Decimal(median_value) * Decimal('0.95')).quantize(Decimal('1')))
    return {
        'rows': rows, 'count': len(prices), 'min_minor': min(prices),
        'max_minor': max(prices), 'median_minor': median_value,
        'suggested_target_minor': suggested,
    }


def negotiation_strategy(q):
    result = price_assistance(q)
    if not result['count']:
        return '暂无足够历史成交价，建议优先核实成本构成、交期、税率和付款条件。'
    return (
        f"共参考 {result['count']} 条历史成交记录。历史中位单价为 "
        f"{Decimal(result['median_minor']) / 100:.2f} 元，建议初始目标价可参考 "
        f"{Decimal(result['suggested_target_minor']) / 100:.2f} 元，并结合规格、数量、"
        "交期、付款条件及技术偏离进行人工调整。"
    )
