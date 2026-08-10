"""Procurement project application service."""

from __future__ import annotations

import io
import os
import tempfile

from datetime import date
from decimal import Decimal, InvalidOperation

import ledger_store
import procurement_store
from services import procurement_file_service
from services.office_parse_service import extract_excel_rows_isolated
from utils.constants import (
    PROCUREMENT_METHOD_LABELS,
    PROCUREMENT_STAGE_LABELS,
    PROCUREMENT_STAGE_ORDER,
    PROCUREMENT_STATUS_LABELS,
)
from utils.money import to_minor, from_minor
from utils.logger import get_logger
from utils.security import MAX_TEXT_VALUE_LENGTH, limit_text, validate_office_archive
from utils.template_paths import safe_template_path


MAX_PROCUREMENT_IMPORT_ROWS = 1000
MAX_PROCUREMENT_QUANTITY = Decimal('1000000000000')
STATUS_TRANSITIONS = {
    'draft': {'documents_ready', 'inquiry_sent', 'quotes_received', 'archived'},
    'documents_ready': {'draft', 'inquiry_sent', 'quotes_received', 'archived'},
    'inquiry_sent': {'documents_ready', 'quotes_received', 'archived'},
    'quotes_received': {'inquiry_sent', 'clarifying', 'negotiating', 'award_draft', 'award_confirmed', 'archived'},
    'clarifying': {'quotes_received', 'negotiating', 'award_draft', 'award_confirmed', 'archived'},
    'negotiating': {'quotes_received', 'clarifying', 'award_draft', 'award_confirmed', 'archived'},
    'award_draft': {'quotes_received', 'award_confirmed', 'archived'},
    'award_confirmed': {'award_draft', 'contract_draft', 'archived'},
    'contract_draft': {'award_confirmed', 'contract_created', 'archived'},
    'contract_created': {'archived'},
    'archived': {'draft', 'contract_created'},
}

STAGE_STATUS_MAP = {
    'project': 'draft',
    'items': 'draft',
    'suppliers': 'draft',
    'quotes': 'quotes_received',
    'comparison': 'clarifying',
    'negotiation': 'negotiating',
    'award': 'award_draft',
    'contract': 'contract_draft',
    'archive': 'archived',
}

STAGE_ACTIONS = {
    'project': {'endpoint': 'procurement_project_edit', 'label': '编辑项目'},
    'items': {'endpoint': 'procurement_project_detail', 'anchor': 'items', 'label': '录入明细'},
    'suppliers': {'endpoint': 'procurement_project_detail', 'anchor': 'suppliers', 'label': '维护供应商'},
    'quotes': {'endpoint': 'procurement_quote_import', 'label': '导入报价'},
    'comparison': {'endpoint': 'procurement_comparison', 'label': '进入比价'},
    'negotiation': {'endpoint': 'procurement_negotiation', 'label': '进入谈判'},
    'award': {'endpoint': 'procurement_award', 'label': '成交建议'},
    'contract': {'endpoint': 'procurement_direct_contract', 'label': '直接生成合同'},
    'archive': {'endpoint': 'procurement_project_archive', 'label': '生成归档包'},
}


def list_projects(*, status='', q='', page=1):
    return procurement_store.list_projects(
        status=status,
        q=q,
        page=page,
    )


def project_statuses():
    return procurement_store.PROJECT_STATUSES


def get_project(project_id):
    return procurement_store.get_project(project_id)


def get_project_item(project_id, item_id):
    item = procurement_store.get_project_item(item_id)
    if not item or item['project_id'] != project_id:
        return None
    return item


def delete_item(project_id, item_id):
    return procurement_store.delete_project_item(project_id, item_id)


def list_suppliers(project_id):
    return procurement_store.list_project_suppliers(project_id)


def get_supplier(project_id, supplier_id):
    supplier = procurement_store.get_project_supplier(supplier_id)
    if not supplier or supplier['project_id'] != project_id:
        return None
    return supplier


def _positive_quantity(value):
    try:
        quantity = Decimal(str(value or '').strip())
    except InvalidOperation as exc:
        raise ValueError('数量格式无效') from exc
    if not quantity.is_finite():
        raise ValueError('数量必须是有限数值')
    if quantity <= 0:
        raise ValueError('数量必须大于 0')
    if quantity > MAX_PROCUREMENT_QUANTITY:
        raise ValueError('数量超出允许范围')
    return quantity


def money_to_minor(value, label='金额', allow_empty=True):
    return to_minor(value, allow_none=allow_empty)


def minor_to_money(value):
    return from_minor(value)


def _next_project_no(conn=None):
    prefix = 'CG-' + date.today().strftime('%Y%m%d') + '-'
    def _read(connection):
        return connection.execute(
            'SELECT project_no FROM procurement_projects WHERE project_no LIKE ? ORDER BY project_no DESC LIMIT 1',
            (prefix + '%',),
        ).fetchone()
    if conn is None:
        with ledger_store.get_conn() as managed_conn:
            rows = _read(managed_conn)
    else:
        rows = _read(conn)
    if not rows:
        return prefix + '0001'
    try:
        sequence = int(rows[0].rsplit('-', 1)[1]) + 1
    except (ValueError, IndexError):
        sequence = 1
    return prefix + f'{sequence:04d}'


def create_project(form):
    import sqlite3
    name = str(form.get('project_name') or '').strip()
    if not name:
        raise ValueError('项目名称不能为空')
    submitted_project_no = str(form.get('project_no') or '').strip()
    data = {
        'project_no': submitted_project_no,
        'project_name': name,
        'purchase_method': str(form.get('purchase_method') or 'competitive_negotiation').strip(),
        'demand_department': str(form.get('demand_department') or '').strip(),
        'owner': str(form.get('owner') or '').strip(),
        'budget_minor': money_to_minor(form.get('budget_amount'), '预算金额'),
        'target_price_minor': money_to_minor(form.get('target_price'), '目标价格'),
        'currency': 'CNY',
        'delivery_place': str(form.get('delivery_place') or '').strip(),
        'delivery_requirement': str(form.get('delivery_requirement') or '').strip(),
        'payment_requirement': str(form.get('payment_requirement') or '').strip(),
        'remark': str(form.get('remark') or '').strip(),
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if submitted_project_no:
                project_id = procurement_store.create_project(data)
            else:
                with ledger_store.get_conn() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    data['project_no'] = _next_project_no(conn)
                    project_id = procurement_store.create_project(
                        data, conn=conn
                    )
            break
        except sqlite3.IntegrityError:
            if submitted_project_no:
                raise ValueError('项目编号已存在')
            if attempt == max_retries - 1:
                raise ValueError('创建项目失败，请稍后重试')
    project = procurement_store.get_project(project_id)
    procurement_file_service.ensure_project_folders(project)
    return project_id


def update_project(project_id, form):
    project = procurement_store.get_project(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    name = str(form.get('project_name') or '').strip()
    if not name:
        raise ValueError('项目名称不能为空')
    return procurement_store.update_project(project_id, {
        'project_name': name,
        'purchase_method': str(form.get('purchase_method') or project['purchase_method']).strip(),
        'demand_department': str(form.get('demand_department') or '').strip(),
        'owner': str(form.get('owner') or '').strip(),
        'budget_minor': money_to_minor(form.get('budget_amount'), '预算金额'),
        'target_price_minor': money_to_minor(form.get('target_price'), '目标价格'),
        'delivery_place': str(form.get('delivery_place') or '').strip(),
        'delivery_requirement': str(form.get('delivery_requirement') or '').strip(),
        'payment_requirement': str(form.get('payment_requirement') or '').strip(),
        'remark': str(form.get('remark') or '').strip(),
    })


def transition(project_id, new_status, note=''):
    project = procurement_store.get_project(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    if new_status == project['status']:
        return
    if new_status not in STATUS_TRANSITIONS.get(project['status'], set()):
        current_label = PROCUREMENT_STATUS_LABELS.get(project['status'], project['status'])
        new_label = PROCUREMENT_STATUS_LABELS.get(new_status, new_status)
        raise ValueError(f'项目不能从“{current_label}”直接变更为“{new_label}”')
    procurement_store.transition_project_status(project_id, new_status, note=note)


def _stage_completion(project):
    return {
        'project': True,
        'items': len(project.get('items') or []) > 0,
        'suppliers': len(project.get('suppliers') or []) > 0,
        'quotes': len(project.get('quotes') or []) > 0,
        'comparison': bool(project.get('comparison') or project.get('clarifications')),
        'negotiation': len(project.get('negotiation_rounds') or []) > 0,
        'award': bool(project.get('award')),
        'contract': len(project.get('contract_links') or []) > 0,
        'archive': project.get('status') == 'archived',
    }


def _stage_applicable(project, stage):
    if project.get('purchase_method') == 'single_source' and stage == 'comparison':
        return False
    return True


def _workflow_skips(project_id):
    skipped = {}
    for event in procurement_store.list_project_audit_events(project_id, actions=['workflow_jump']):
        after = event.get('after') or {}
        note = event.get('note') or ''
        for stage in after.get('skipped_stages') or []:
            skipped.setdefault(stage, {
                'note': note,
                'target_stage': after.get('target_stage') or '',
                'created_at': event.get('created_at') or '',
            })
    return skipped


def _missing_before(project, target_stage):
    completion = _stage_completion(project)
    missing = []
    for stage in PROCUREMENT_STAGE_ORDER:
        if stage == target_stage:
            break
        if stage == 'project':
            continue
        if not _stage_applicable(project, stage):
            continue
        if not completion.get(stage):
            missing.append(stage)
    return missing


def build_workflow_view(project_id):
    project = project_detail(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    completion = _stage_completion(project)
    skipped = _workflow_skips(project_id)
    recommended_key = None
    for stage in PROCUREMENT_STAGE_ORDER:
        if not _stage_applicable(project, stage):
            continue
        if not completion.get(stage) and stage not in skipped:
            recommended_key = stage
            break
    if recommended_key is None:
        recommended_key = 'archive'

    stages = []
    for stage in PROCUREMENT_STAGE_ORDER:
        applicable = _stage_applicable(project, stage)
        done = completion.get(stage, False)
        skipped_info = skipped.get(stage)
        missing_before = _missing_before(project, stage) if applicable else []
        requires_skip_note = bool(missing_before and not done and not skipped_info)
        if not applicable:
            status = 'not_applicable'
        elif done:
            status = 'done'
        elif skipped_info:
            status = 'skipped'
        elif stage == recommended_key:
            status = 'active'
        elif missing_before:
            status = 'available'
        else:
            status = 'available'
        stages.append({
            'key': stage,
            'label': PROCUREMENT_STAGE_LABELS.get(stage, stage),
            'status': status,
            'applicable': applicable,
            'done': done,
            'skipped': bool(skipped_info),
            'skip_note': (skipped_info or {}).get('note', ''),
            'missing_before': missing_before,
            'missing_labels': [PROCUREMENT_STAGE_LABELS.get(item, item) for item in missing_before],
            'requires_skip_note': requires_skip_note,
            'action': STAGE_ACTIONS.get(stage, {}),
        })
    return {
        'status_label': PROCUREMENT_STATUS_LABELS.get(project.get('status'), project.get('status')),
        'method_label': PROCUREMENT_METHOD_LABELS.get(
            project.get('purchase_method'), project.get('purchase_method')
        ),
        'recommended_stage': recommended_key,
        'recommended_label': PROCUREMENT_STAGE_LABELS.get(recommended_key, recommended_key),
        'stages': stages,
    }


def jump_to_stage(project_id, target_stage, note=''):
    if target_stage not in PROCUREMENT_STAGE_ORDER:
        raise ValueError('采购环节无效')
    project = project_detail(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    if not _stage_applicable(project, target_stage):
        return target_stage
    if target_stage == 'negotiation' and not project.get('suppliers'):
        raise ValueError('进入谈判前至少需要添加一个候选供应商')
    note = str(note or '').strip()
    completion = _stage_completion(project)
    skipped = _workflow_skips(project_id)
    missing = _missing_before(project, target_stage)
    target_already_available = completion.get(target_stage) or target_stage in skipped
    if target_already_available:
        missing = []
    if missing and not note:
        raise ValueError('跳过前置环节时需要填写原因')
    before_status = project.get('status') or ''
    next_status = STAGE_STATUS_MAP.get(target_stage, before_status)
    if target_already_available:
        next_status = before_status
    if next_status != before_status:
        procurement_store.transition_project_status(project_id, next_status, note=note)
    procurement_store.record_workflow_jump(
        project_id, target_stage, missing, note=note,
        before_status=before_status, after_status=next_status,
    )
    return target_stage


def add_item(project_id, form):
    if not procurement_store.get_project(project_id):
        raise ValueError('采购项目不存在')
    item_name = str(form.get('item_name') or '').strip()
    unit = str(form.get('unit') or '').strip()
    if not item_name:
        raise ValueError('物资名称不能为空')
    if not unit:
        raise ValueError('单位不能为空')
    quantity = _positive_quantity(form.get('quantity'))
    normalized = format(quantity.normalize(), 'f')
    return procurement_store.add_project_item(project_id, {
        'item_name': item_name,
        'spec_model': str(form.get('spec_model') or '').strip(),
        'drawing_no': str(form.get('drawing_no') or '').strip(),
        'quantity_text': normalized,
        'unit': unit,
        'required_delivery_date': str(form.get('required_delivery_date') or '').strip(),
        'technical_requirement': str(form.get('technical_requirement') or '').strip(),
        'remark': str(form.get('remark') or '').strip(),
    })


def update_item(project_id, item_id, form):
    item_name = str(form.get('item_name') or '').strip()
    unit = str(form.get('unit') or '').strip()
    if not item_name or not unit:
        raise ValueError('物资名称和单位不能为空')
    quantity = _positive_quantity(form.get('quantity'))
    procurement_store.update_project_item(project_id, item_id, {
        'item_name': item_name,
        'spec_model': str(form.get('spec_model') or '').strip(),
        'drawing_no': str(form.get('drawing_no') or '').strip(),
        'quantity_text': format(quantity.normalize(), 'f'),
        'unit': unit,
        'required_delivery_date': str(form.get('required_delivery_date') or '').strip(),
        'technical_requirement': str(form.get('technical_requirement') or '').strip(),
        'remark': str(form.get('remark') or '').strip(),
    })


def add_items_from_rows(project_id, rows):
    parsed = []
    errors = []
    for row_number, row in enumerate(rows, start=1):
        if row_number > MAX_PROCUREMENT_IMPORT_ROWS:
            raise ValueError(f'采购明细一次最多导入 {MAX_PROCUREMENT_IMPORT_ROWS} 行')
        values = list(row) + [''] * 8
        if not any(str(value or '').strip() for value in values):
            continue
        item_name = limit_text(values[0], MAX_TEXT_VALUE_LENGTH).strip()
        unit = limit_text(values[4], 120).strip()
        try:
            quantity = _positive_quantity(values[3])
        except ValueError as exc:
            errors.append(f'第 {row_number} 行{exc}')
            continue
        if not item_name or not unit:
            errors.append(f'第 {row_number} 行物资名称、正数数量和单位为必填项')
            continue
        parsed.append({
            'item_name': item_name, 'spec_model': limit_text(values[1], 1000).strip(),
            'drawing_no': limit_text(values[2], 500).strip(),
            'quantity_text': format(quantity.normalize(), 'f'), 'unit': unit,
            'required_delivery_date': limit_text(values[5], 120).strip(),
            'technical_requirement': limit_text(values[6], MAX_TEXT_VALUE_LENGTH).strip(),
            'remark': limit_text(values[7], 2000).strip(),
        })
    if errors:
        raise ValueError('；'.join(errors[:20]))
    if not parsed:
        raise ValueError('没有可导入的采购明细')
    return procurement_store.add_project_items_bulk(project_id, parsed)


def add_items_from_paste(project_id, text):
    rows = (line.rstrip('\r\n').split('\t') for line in io.StringIO(str(text or '')))
    return add_items_from_rows(project_id, rows)


def add_items_from_excel(project_id, file_storage):
    filename = str(getattr(file_storage, 'filename', '') or '')
    if not filename.lower().endswith('.xlsx'):
        raise ValueError('采购明细批量导入仅支持 .xlsx 格式')
    temp_path = ''
    try:
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            temp_path = temp_file.name
        file_storage.save(temp_path)
        validate_office_archive(temp_path)
        try:
            extracted_rows = extract_excel_rows_isolated(
                temp_path,
                max_rows=MAX_PROCUREMENT_IMPORT_ROWS + 1,
                max_columns=50,
            )
        except ValueError as exc:
            if str(MAX_PROCUREMENT_IMPORT_ROWS + 1) in str(exc):
                raise ValueError(
                    f'一次最多导入 {MAX_PROCUREMENT_IMPORT_ROWS} 条采购明细'
                ) from exc
            raise
        first = extracted_rows[0] if extracted_rows else None
        if first is None:
            raise ValueError('没有可导入的采购明细')
        if str(first[0] or '').strip() not in {'物资名称', '产品名称', '标的名称'}:
            rows = extracted_rows
        else:
            rows = extracted_rows[1:]
        return add_items_from_rows(project_id, rows)
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                get_logger().debug('Procurement import temp file already absent: %s', temp_path)


def add_supplier(project_id, form):
    if not procurement_store.get_project(project_id):
        raise ValueError('采购项目不存在')
    supplier_name = str(form.get('supplier_name') or '').strip()
    if not supplier_name:
        raise ValueError('供应商名称不能为空')
    return procurement_store.add_project_supplier(project_id, {
        'supplier_name': supplier_name,
        'contact_person': str(form.get('contact_person') or '').strip(),
        'contact_phone': str(form.get('contact_phone') or '').strip(),
        'email': str(form.get('email') or '').strip(),
        'direct_support_experience': str(form.get('direct_support_experience') or '').strip(),
        'aerospace_support_experience': str(form.get('aerospace_support_experience') or '').strip(),
        'qualifications': str(form.get('qualifications') or '').strip(),
        'remark': str(form.get('remark') or '').strip(),
    })


def update_supplier(project_id, supplier_id, form):
    supplier_name = str(form.get('supplier_name') or '').strip()
    if not supplier_name:
        raise ValueError('供应商名称不能为空')
    procurement_store.update_project_supplier(project_id, supplier_id, {
        'supplier_name': supplier_name,
        'contact_person': str(form.get('contact_person') or '').strip(),
        'contact_phone': str(form.get('contact_phone') or '').strip(),
        'email': str(form.get('email') or '').strip(),
        'direct_support_experience': str(form.get('direct_support_experience') or '').strip(),
        'aerospace_support_experience': str(form.get('aerospace_support_experience') or '').strip(),
        'qualifications': str(form.get('qualifications') or '').strip(),
        'remark': str(form.get('remark') or '').strip(),
    })


def delete_supplier(project_id, supplier_id):
    relative_paths = procurement_store.delete_project_supplier(project_id, supplier_id)
    for relative_path in relative_paths:
        try:
            procurement_file_service.absolute_path(relative_path).unlink(missing_ok=True)
        except (OSError, ValueError):
            get_logger().warning(
                '删除供应商临时报价文件失败: %s', relative_path, exc_info=True
            )


def prepare_direct_contract_session(project_id, template_filename, paths):
    project = project_detail(project_id)
    if not project:
        raise ValueError('采购项目不存在')
    path = safe_template_path(template_filename, paths)
    primary_supplier = (project.get('suppliers') or [{}])[0]
    amount_minor = project.get('target_price_minor') or project.get('budget_minor') or 0
    payload = {
        'schema_version': 'direct-1.0',
        'project_id': project_id,
        'project_no': project['project_no'],
        'project_name': project['project_name'],
        'award_recommendation_id': None,
        'supplier': {
            'id': primary_supplier.get('id'),
            'name': primary_supplier.get('supplier_name') or '',
        },
        'suppliers': [row.get('supplier_name') for row in project.get('suppliers', []) if row.get('supplier_name')],
        'currency': project.get('currency') or 'CNY',
        'amount_minor': amount_minor,
        'items': [
            {
                'project_item_id': item['id'],
                'item_name': item['item_name'],
                'spec_model': item.get('spec_model') or '',
                'quantity': item.get('quantity_text') or '',
                'unit': item.get('unit') or '',
                'unit_price': '',
                'amount': '',
                'supplier_name': primary_supplier.get('supplier_name') or '',
            }
            for item in project.get('items', [])
        ],
        'delivery_place': project.get('delivery_place') or '',
        'delivery_terms': project.get('delivery_requirement') or '',
        'payment_terms': project.get('payment_requirement') or '',
        'warranty_period': '',
        'technical_notes': '',
        'commercial_notes': '',
        'contract_notice': project.get('remark') or '',
        'owner': project.get('owner') or '',
        'demand_department': project.get('demand_department') or '',
        'source_quote_ids': [],
    }
    from services import award_service
    tpl, fields = award_service.prepare_template_fields(path, payload)
    return {
        'template_name': tpl.name,
        'template_path': path,
        'template_filename': template_filename,
        'stored_name': tpl.data.get('source_docx', ''),
        'fields': fields,
        'initial_values': payload,
        'source_project_id': project_id,
        'source_type': 'direct_contract',
        'procurement_project_id': project_id,
        'project_name': project['project_name'],
        'step': 'editor',
    }


def project_detail(project_id):
    project = procurement_store.get_project(project_id)
    if not project:
        return None
    project['budget_amount'] = minor_to_money(project.get('budget_minor'))
    project['target_price'] = minor_to_money(project.get('target_price_minor'))
    project['items'] = procurement_store.list_project_items(project_id)
    project['suppliers'] = procurement_store.list_project_suppliers(project_id)
    project['quotes'] = procurement_store.list_quotes(project_id)
    project['clarifications'] = procurement_store.list_clarifications(project_id)
    project['comparison'] = procurement_store.get_latest_comparison(project_id)
    project['negotiation_rounds'] = procurement_store.list_negotiation_rounds(project_id)
    project['award'] = procurement_store.get_latest_award(project_id)
    project['contract_links'] = procurement_store.get_project_contract_links(project_id)
    project['files'] = procurement_store.list_project_files(project_id)
    return project
