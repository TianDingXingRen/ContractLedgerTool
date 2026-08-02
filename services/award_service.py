"""Award recommendation and procurement-to-contract handoff."""

from __future__ import annotations

from copy import deepcopy

import procurement_store
import template_def
from utils.keyword_maps import find_scalar_semantic, find_column_semantic
from utils.money import from_minor
from utils.template_paths import safe_template_path


_SCALAR_SEMANTIC_TO_PAYLOAD = {
    'contract_no': lambda payload: f"{payload['project_no']}-HT",
    'project_no': lambda payload: payload['project_no'],
    'title': lambda payload: payload['project_name'],
    'counterparty': lambda payload: payload['supplier']['name'],
    'amount': lambda payload: from_minor(payload['amount_minor']),
    'delivery_place': lambda payload: payload['delivery_place'],
    'delivery_terms': lambda payload: payload['delivery_terms'],
    'payment_terms': lambda payload: payload['payment_terms'],
    'warranty': lambda payload: payload['warranty_period'],
    'technical_notes': lambda payload: payload['technical_notes'],
    'commercial_notes': lambda payload: payload['commercial_notes'],
    'contract_notice': lambda payload: payload['contract_notice'],
    'owner': lambda payload: payload['owner'],
    'demand_department': lambda payload: payload['demand_department'],
}


_COLUMN_SEMANTIC_TO_VALUE = {
    'line_no': lambda index, item, _supplier_name: index,
    'item_name': lambda _index, item, _supplier_name: item['item_name'],
    'supplier': lambda _index, item, supplier_name: item.get('supplier_name') or supplier_name,
    'spec_model': lambda _index, item, _supplier_name: item['spec_model'],
    'quantity': lambda _index, item, _supplier_name: item['quantity'],
    'unit': lambda _index, item, _supplier_name: item['unit'],
    'unit_price': lambda _index, item, _supplier_name: item['unit_price'],
    'amount': lambda _index, item, _supplier_name: item['amount'],
}


def _field_semantic(field):
    label = str(field.get('label') or '')
    key = str(field.get('key') or '')
    return find_scalar_semantic(label, key)


def _col_semantic(column):
    label = str(column.get('label') or '')
    key = str(column.get('key') or '')
    return find_column_semantic(label, key)


def create_award(project_id, supplier_id, form):
    project = procurement_store.get_project(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    quotes = procurement_store.get_latest_quotes(project_id)
    quote = next((row for row in quotes if row['supplier_id'] == int(supplier_id)), None)
    if not quote:
        raise ValueError('所选供应商没有有效报价')
    items = procurement_store.get_quote_items(quote['id'])
    project_items = procurement_store.list_project_items(project_id)
    if len(items) != len(project_items):
        raise ValueError('所选供应商报价存在漏项，不能直接确认成交')
    complete_totals = [
        row['total_amount_minor'] for row in quotes
        if len(procurement_store.get_quote_items(row['id'])) == len(project_items)
    ]
    lowest = min(complete_totals)
    not_lowest_reason = str(form.get('lowest_price_not_selected_reason') or '').strip()
    if quote['total_amount_minor'] > lowest and not not_lowest_reason:
        raise ValueError('未选择最低总价供应商时必须填写原因')
    reason = str(form.get('reason_summary') or '').strip()
    if not reason:
        reason = '综合价格、技术响应、商务响应和交付保障，建议选择该供应商。'
    data = {
        'recommended_amount_minor': quote['total_amount_minor'],
        'currency': quote.get('currency') or 'CNY',
        'reason_summary': reason,
        'price_reason': str(form.get('price_reason') or '').strip(),
        'technical_reason': str(form.get('technical_reason') or '').strip(),
        'commercial_reason': str(form.get('commercial_reason') or '').strip(),
        'delivery_reason': str(form.get('delivery_reason') or '').strip(),
        'risk_note': str(form.get('risk_note') or '').strip(),
        'lowest_price_not_selected_reason': not_lowest_reason,
        'contract_notice': str(form.get('contract_notice') or '').strip(),
    }
    return procurement_store.create_award_recommendation(
        project_id, quote['supplier_id'], quote['id'], data, items
    )


def split_award_options(project_id):
    project_items = procurement_store.list_project_items(project_id)
    quotes = procurement_store.get_latest_quotes(project_id)
    quote_items = {}
    for quote in quotes:
        for item in procurement_store.get_quote_items(quote['id']):
            enriched = dict(item)
            enriched.update({
                'supplier_id': quote['supplier_id'], 'supplier_name': quote['supplier_name'],
                'quote_id': quote['id'], 'quote_round': quote['quote_round'],
            })
            quote_items[item['id']] = enriched
    rows = []
    for project_item in project_items:
        options = [item for item in quote_items.values() if item['project_item_id'] == project_item['id']]
        options.sort(key=lambda item: item['unit_price_minor'])
        rows.append({'item': project_item, 'options': options})
    return rows, quote_items


def create_split_award(project_id, form):
    rows, quote_items = split_award_options(project_id)
    selections = []
    selected_above_lowest = False
    for row in rows:
        raw = form.get(f"selection_{row['item']['id']}")
        try:
            selected = quote_items[int(raw)]
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError(f"请选择“{row['item']['item_name']}”的成交供应商") from exc
        selections.append(selected)
        if row['options'] and selected['unit_price_minor'] > row['options'][0]['unit_price_minor']:
            selected_above_lowest = True
    reason_not_lowest = str(form.get('lowest_price_not_selected_reason') or '').strip()
    if selected_above_lowest and not reason_not_lowest:
        raise ValueError('存在未选择最低单价的明细，必须填写原因')
    data = {
        'reason_summary': str(form.get('reason_summary') or '').strip()
                          or '根据分项价格、技术响应和交付能力，建议按明细拆分成交。',
        'price_reason': str(form.get('price_reason') or '').strip(),
        'technical_reason': str(form.get('technical_reason') or '').strip(),
        'commercial_reason': str(form.get('commercial_reason') or '').strip(),
        'delivery_reason': str(form.get('delivery_reason') or '').strip(),
        'risk_note': str(form.get('risk_note') or '').strip(),
        'lowest_price_not_selected_reason': reason_not_lowest,
        'contract_notice': str(form.get('contract_notice') or '').strip(),
    }
    return procurement_store.create_split_award_recommendation(project_id, data, selections)


def award_view(project_id):
    split_rows, _ = split_award_options(project_id)
    return {
        'quotes': procurement_store.get_latest_quotes(project_id),
        'split_rows': split_rows,
        'award': procurement_store.get_latest_award(project_id),
    }


def get_latest_award(project_id):
    return procurement_store.get_latest_award(project_id)


def list_contract_templates():
    return template_def.list_templates()


def build_contract_data_sheet(project_id):
    project = procurement_store.get_project(project_id)
    award = procurement_store.get_latest_award(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    if not award:
        raise ValueError('请先确认成交建议')
    payload = {
        'schema_version': '1.0',
        'project_id': project_id,
        'project_no': project['project_no'],
        'project_name': project['project_name'],
        'award_recommendation_id': award['id'],
        'supplier': {
            'id': award['supplier_id'],
            'name': award.get('supplier_summary') or award['supplier_name'],
        },
        'suppliers': list(dict.fromkeys(
            item.get('supplier_name') for item in award['items'] if item.get('supplier_name')
        )),
        'currency': award['currency'],
        'amount_minor': award['recommended_amount_minor'],
        'items': [
            {
                'project_item_id': item['project_item_id'],
                'item_name': item['item_name'],
                'spec_model': item.get('spec_model') or '',
                'quantity': item['quantity_text'],
                'unit': item['unit'],
                'unit_price': from_minor(item['unit_price_minor']),
                'amount': from_minor(item['amount_minor']),
                'supplier_name': item.get('supplier_name') or award['supplier_name'],
            }
            for item in award['items']
        ],
        'delivery_place': project.get('delivery_place') or '',
        'delivery_terms': award.get('delivery_period') or project.get('delivery_requirement') or '',
        'payment_terms': award.get('payment_terms') or project.get('payment_requirement') or '',
        'warranty_period': award.get('warranty_period') or '',
        'technical_notes': award.get('technical_reason') or award.get('technical_deviation') or '',
        'commercial_notes': award.get('commercial_reason') or award.get('commercial_deviation') or '',
        'contract_notice': award.get('contract_notice') or '',
        'owner': project.get('owner') or '',
        'demand_department': project.get('demand_department') or '',
        'source_quote_ids': list(dict.fromkeys(
            item.get('quote_id') for item in award['items'] if item.get('quote_id')
        )) or [award['quote_id']],
    }
    return procurement_store.get_or_create_contract_data_sheet(project_id, award['id'], payload)


def _scalar_value(field, payload):
    semantic = _field_semantic(field)
    if semantic and semantic in _SCALAR_SEMANTIC_TO_PAYLOAD:
        return _SCALAR_SEMANTIC_TO_PAYLOAD[semantic](payload)
    return field.get('default_value') or ''


def _table_rows(field, payload):
    supplier_name = payload['supplier']['name']
    rows = []
    for index, item in enumerate(payload['items'], start=1):
        row = {}
        for column in field.get('columns', []):
            semantic = _col_semantic(column)
            if semantic and semantic in _COLUMN_SEMANTIC_TO_VALUE:
                value = _COLUMN_SEMANTIC_TO_VALUE[semantic](index, item, supplier_name)
            else:
                value = column.get('default_value') or ''
            row[column.get('key')] = value
        rows.append(row)
    return rows


def prepare_template_fields(template_path, payload):
    tpl = template_def.TemplateDef.load(template_path)
    fields = deepcopy(tpl.data.get('fields') or [])
    for index, field in enumerate(fields):
        field.setdefault('id', index)
        if field.get('field_type') == 'table':
            field['default_rows'] = _table_rows(field, payload)
        elif field.get('field_type') != 'calculated':
            field['default_value'] = _scalar_value(field, payload)
    return tpl, fields


def prepare_editor_session(project_id, template_filename, paths):
    sheet = build_contract_data_sheet(project_id)
    sheet = procurement_store.get_contract_data_sheet(sheet['id'])
    path = safe_template_path(template_filename, paths)
    tpl, fields = prepare_template_fields(path, sheet['payload'])
    procurement_store.mark_data_sheet_in_editor(sheet['id'])
    return {
        'template_name': tpl.name,
        'template_path': path,
        'template_filename': template_filename,
        'stored_name': tpl.data.get('source_docx', ''),
        'fields': fields,
        'initial_values': sheet['payload'],
        'procurement_data_sheet_id': sheet['id'],
        'procurement_project_id': project_id,
        'source_project_id': project_id,
        'source_type': 'award',
        'source_id': sheet['payload'].get('award_recommendation_id'),
        'project_name': sheet['payload']['project_name'],
        'step': 'editor',
    }
