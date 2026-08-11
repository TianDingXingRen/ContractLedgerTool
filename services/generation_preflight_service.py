"""Preflight checks before contract generation."""

from __future__ import annotations

import ledger_store
from utils.generation_utils import contract_number_keys, infer_contract_summary


def _summary_warnings(summary):
    warnings = []
    if not summary.get('amount'):
        warnings.append('未识别到合同金额，台账金额将为空')
    if not summary.get('sign_date'):
        warnings.append('未识别到签订日期，台账签订日期将为空')
    if not summary.get('counterparty'):
        warnings.append('未识别到对方单位，台账对方单位将为空')
    return warnings


def build_single_preflight(tpl, fields, field_values, classification):
    summary = infer_contract_summary(tpl, fields, field_values)
    summary.update(classification or {})
    blocking = []
    warnings = _summary_warnings(summary)
    contract_no = str(summary.get('contract_no') or '').strip()
    if contract_no and ledger_store.contract_no_exists(contract_no):
        blocking.append(f'合同编号 {contract_no} 已存在，请修改后再生成')
    return {
        'ok': not blocking,
        'mode': 'single',
        'blocking': blocking,
        'warnings': warnings,
        'summary': {
            'template': tpl.name,
            'contract_no': contract_no,
            'counterparty': summary.get('counterparty') or '',
            'amount': summary.get('amount'),
            'sign_date': summary.get('sign_date') or '',
            'project_name': summary.get('project_name') or '',
            'subsystem_name': summary.get('subsystem_name') or '',
            'coverage_mode': summary.get('coverage_mode') or '',
            'coverage_not_applicable': bool(
                summary.get('coverage_not_applicable')
            ),
            'coverage_start': summary.get('coverage_start'),
            'coverage_end': summary.get('coverage_end'),
            'ledger': True,
        },
    }


def build_batch_preflight(
    tpl,
    fields,
    field_values,
    classification,
    counterparties,
    batch_field_keys,
):
    blocking = []
    warnings = []
    if not counterparties:
        blocking.append('请至少输入一个对方单位')
    if not batch_field_keys:
        blocking.append('未能识别对方单位字段，请手动指定字段变量名')

    number_keys = contract_number_keys(fields)
    duplicate_numbers = []
    if number_keys:
        for index, _counterparty in enumerate(counterparties, start=1):
            for number_key in number_keys:
                base_number = str(field_values.get(number_key) or '').strip()
                if not base_number:
                    continue
                candidate = f'{base_number}-{index:03d}'
                if ledger_store.contract_no_exists(candidate):
                    duplicate_numbers.append(candidate)
    if duplicate_numbers:
        preview = '、'.join(duplicate_numbers[:5])
        suffix = ' 等' if len(duplicate_numbers) > 5 else ''
        blocking.append(f'批量合同编号已存在：{preview}{suffix}')

    return {
        'ok': not blocking,
        'mode': 'batch',
        'blocking': blocking,
        'warnings': warnings,
        'summary': {
            'template': tpl.name,
            'count': len(counterparties),
            'counterparties_preview': counterparties[:5],
            'batch_field_keys': batch_field_keys,
            'project_name': (classification or {}).get('project_name') or '',
            'subsystem_name': (classification or {}).get('subsystem_name') or '',
            'coverage_mode': (classification or {}).get('coverage_mode') or '',
            'coverage_not_applicable': bool(
                (classification or {}).get('coverage_not_applicable')
            ),
            'coverage_start': (classification or {}).get('coverage_start'),
            'coverage_end': (classification or {}).get('coverage_end'),
            'ledger': True,
        },
    }
