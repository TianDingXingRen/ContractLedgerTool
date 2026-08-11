"""Regression coverage for defects found in the August 2026 code audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading

import pytest


def test_coverage_choice_is_serialized_across_concurrent_updates(tmp_db):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {'title': '并发发次测试', 'project_name': '并发项目'}, {}, '/tmp/a.docx'
    )
    barrier = threading.Barrier(2)
    outcomes = []

    def update(values):
        barrier.wait()
        try:
            ledger_store.update_contract(contract_id, values)
            outcomes.append('ok')
        except ValueError:
            outcomes.append('rejected')

    threads = [
        threading.Thread(
            target=update,
            args=({'coverage_start': 1, 'coverage_end': 2},),
        ),
        threading.Thread(
            target=update,
            args=(
                {
                    'coverage_not_applicable': 1,
                    'coverage_start': None,
                    'coverage_end': None,
                },
            ),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ['ok', 'rejected']
    contract = ledger_store.get_contract(contract_id)
    has_range = contract['coverage_start'] == 1 and contract['coverage_end'] == 2
    is_not_applicable = bool(contract['coverage_not_applicable'])
    assert has_range != is_not_applicable


def test_void_contract_is_excluded_and_cannot_receive_payment(tmp_db):
    import ledger_store
    from services import payment_commands

    contract_id = ledger_store.create_contract(
        {'title': '待作废合同', 'status': 'signed'}, {}, '/tmp/void.docx'
    )
    plan_id = ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '尾款',
            'confirm_status': 'confirmed',
            'due_date': '2026-01-01',
            'due_amount': 100,
        },
    )

    ledger_store.update_contract(contract_id, {'status': 'void'})

    assert ledger_store.list_payment_plans(page=1)['total'] == 0
    assert ledger_store.summarize_payment_plans(today=None)['count'] == 0
    assert ledger_store.get_payment_stats()['total_due'] == 0
    with pytest.raises(ValueError, match='已作废合同'):
        payment_commands.quick_update_payment_plan(
            plan_id, 'paid', paid_date='2026-08-11'
        )


def test_contract_with_financial_execution_cannot_be_voided(tmp_db):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {'title': '已付款合同', 'status': 'signed'}, {}, '/tmp/paid.docx'
    )
    ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '首款',
            'confirm_status': 'confirmed',
            'due_amount': 100,
            'paid_amount': 50,
            'paid_date': '2026-08-01',
        },
    )

    with pytest.raises(ValueError, match='不能直接作废'):
        ledger_store.update_contract(contract_id, {'status': 'void'})
    assert ledger_store.get_contract(contract_id)['status'] == 'signed'


def test_project_view_searches_contract_and_plan_subsystems(tmp_db):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {
            'title': '分系统检索合同',
            'project_name': '搜索项目',
            'subsystem_name': '动力分系统',
        },
        {},
        '/tmp/search.docx',
    )
    groups = ledger_store.list_project_grouped_contracts(q='动力分系统')
    assert groups[0][1][0]['id'] == contract_id

    ledger_store.update_contract(contract_id, {'subsystem_name': ''})
    ledger_store.insert_payment_plan(
        contract_id, {'phase_name': '节点', 'subsystem_name': '控制分系统'}
    )
    groups = ledger_store.list_project_grouped_contracts(q='控制分系统')
    assert groups[0][1][0]['id'] == contract_id


def test_blank_plan_subsystem_tracks_contract_corrections(tmp_db):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {
            'title': '继承分系统合同',
            'project_name': '继承项目',
            'subsystem_name': '原分系统',
        },
        {},
        '/tmp/inherit.docx',
    )
    plan_id = ledger_store.insert_payment_plan(
        contract_id,
        {
            'phase_name': '节点',
            'confirm_status': 'confirmed',
            'due_date': '2026-08-20',
            'due_amount': 10,
        },
    )
    assert ledger_store.get_payment_plan(plan_id)['subsystem_name'] == ''

    ledger_store.update_contract(contract_id, {'subsystem_name': '新分系统'})
    plan = ledger_store.get_payment_plan(plan_id)
    assert plan['contract_subsystem_name'] == '新分系统'
    report = ledger_store.build_monthly_payment_report('2026-08')
    assert report['rows'][0]['subsystem_name'] == '新分系统'


def test_batch_delete_writes_history_for_every_contract(tmp_db):
    import ledger_store

    ids = [
        ledger_store.create_contract({'title': title}, {}, f'/tmp/{title}.docx')
        for title in ('批删甲', '批删乙')
    ]
    assert ledger_store.batch_delete_contracts(ids) == 2
    for contract_id in ids:
        assert any(
            row['field'] == 'deleted_at'
            for row in ledger_store.get_contract_history(contract_id)
        )


def test_direct_ledger_import_honors_runtime_directory(tmp_path):
    runtime_dir = tmp_path / 'isolated-runtime'
    environment = dict(os.environ)
    environment['CONTRACT_TOOL_RUNTIME_DIR'] = str(runtime_dir)
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import os, ledger_store; print(os.path.abspath(ledger_store.DB_PATH))',
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    expected = os.path.abspath(runtime_dir / 'data' / 'contracts.db')
    assert result.stdout.strip() == expected


def test_project_file_versions_are_unique_under_concurrency(tmp_db):
    import procurement_store

    procurement_store.init_db()
    project_id = procurement_store.create_project(
        {'project_no': 'AUDIT-CONCURRENT', 'project_name': '并发文件项目'}
    )
    barrier = threading.Barrier(2)
    errors = []

    def register(filename):
        barrier.wait()
        try:
            procurement_store.register_project_file(
                project_id,
                'inquiry_letter',
                f'procurement/AUDIT-CONCURRENT/{filename}',
                original_name=filename,
            )
        except Exception as exc:  # pragma: no cover - assertion reports detail
            errors.append(exc)

    threads = [
        threading.Thread(target=register, args=('a.docx',)),
        threading.Thread(target=register, args=('b.docx',)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    versions = sorted(
        row['version'] for row in procurement_store.list_project_files(project_id)
    )
    assert versions == [1, 2]


def test_file_digest_wrappers_share_streaming_semantics(tmp_path):
    from services.contract_import_service import ContractImportService
    from services.handover_archive import sha256_file as handover_sha256
    from services.procurement_file_service import sha256_file as procurement_sha256

    path = tmp_path / 'payload.bin'
    payload = (b'contract-ledger-audit' * 80_000) + b'end'
    path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()

    assert ContractImportService.sha256_file(path) == expected
    assert handover_sha256(path) == expected
    assert procurement_sha256(path) == expected


def test_payment_tab_embeds_valid_json_without_plans(client):
    import ledger_store

    contract_id = ledger_store.create_contract(
        {'title': '零付款计划合同'}, {}, '/tmp/no-plans.docx'
    )
    response = client.get(f'/contracts/{contract_id}?tab=payments')
    assert response.status_code == 200
    match = re.search(
        r'<script id="contract-payment-field-data" type="application/json">'
        r'(.*?)</script>',
        response.get_data(as_text=True),
        flags=re.DOTALL,
    )
    assert match
    assert json.loads(match.group(1)) == {'newPlanDrawer': ''}
