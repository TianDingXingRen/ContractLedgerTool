"""P1 regressions for production, recovery paths, and procurement final states."""

from __future__ import annotations

import threading

import pytest


def _production_notice_fixture(ledger_store, *, notice_no='PN-P1-001'):
    contract_id = ledger_store.create_contract(
        {
            'contract_no': f'C-{notice_no}',
            'title': '投产状态回归合同',
            'status': 'signed',
        },
        {},
        '',
    )
    item_id = ledger_store.save_contract_items(contract_id, [{
        'line_no': 1,
        'item_name': '状态回归产品',
        'contracted_qty': 10,
        'unit': '件',
        'unit_price': 100,
    }])[0]
    header = {'notice_no': notice_no, 'notice_date': '2026-08-11'}
    rows = [{'contract_item_id': item_id, 'notice_qty': '2'}]
    notice_id = ledger_store.create_production_notice(
        contract_id, header, rows
    )
    return contract_id, item_id, notice_id, header, rows


def test_void_contract_rejects_production_notice_create_edit_and_issue(tmp_db):
    import ledger_store

    contract_id, item_id, notice_id, header, rows = _production_notice_fixture(
        ledger_store
    )
    ledger_store.update_contract(contract_id, {'status': 'void'})

    with pytest.raises(ValueError, match='已作废合同'):
        ledger_store.create_production_notice(
            contract_id,
            {'notice_no': 'PN-P1-002', 'notice_date': '2026-08-11'},
            [{'contract_item_id': item_id, 'notice_qty': '1'}],
        )
    with pytest.raises(ValueError, match='已作废合同'):
        ledger_store.save_production_notice_draft(
            notice_id, {**header, 'remark': '不应保存'}, rows
        )
    with pytest.raises(ValueError, match='已作废合同'):
        ledger_store.issue_production_notice(notice_id)

    notice = ledger_store.get_production_notice(notice_id)
    assert notice['status'] == 'draft'
    assert notice['remark'] == ''
    assert [event['action'] for event in notice['history']] == ['create']


def test_void_contract_disables_production_and_invoice_actions(client):
    import ledger_store

    contract_id, _item_id, notice_id, _header, _rows = (
        _production_notice_fixture(
            ledger_store, notice_no='PN-P1-VOID-UI'
        )
    )
    ledger_store.issue_production_notice(notice_id)
    ledger_store.update_contract(contract_id, {'status': 'void'})

    detail = client.get(f'/production-notices/{notice_id}')
    contract_page = client.get(
        f'/contracts/{contract_id}?tab=production'
    )

    assert detail.status_code == 200
    assert contract_page.status_code == 200
    detail_html = detail.get_data(as_text=True)
    assert '已作废合同不能登记发票分摊' in detail_html
    assert f'/invoices/new?contract_id={contract_id}' not in detail_html
    assert '已作废合同不能创建或签发投产通知' in (
        contract_page.get_data(as_text=True)
    )


def test_concurrent_acknowledge_and_close_cannot_reopen_closed_notice(tmp_db):
    import ledger_store

    _contract_id, _item_id, notice_id, _header, _rows = (
        _production_notice_fixture(ledger_store, notice_no='PN-P1-RACE')
    )
    ledger_store.issue_production_notice(notice_id)
    barrier = threading.Barrier(2)
    outcomes = []

    def run(action):
        barrier.wait()
        try:
            action(notice_id, '并发测试')
            outcomes.append('ok')
        except ValueError:
            outcomes.append('rejected')

    threads = [
        threading.Thread(target=run, args=(ledger_store.acknowledge_production_notice,)),
        threading.Thread(target=run, args=(ledger_store.close_production_notice,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads)
    assert outcomes.count('ok') >= 1
    notice = ledger_store.get_production_notice(notice_id)
    assert notice['status'] == 'closed'
    assert notice['history'][0]['action'] == 'close'


@pytest.mark.parametrize('unsafe_field', ['output_path', 'staging_path'])
def test_recovery_marks_unsafe_journal_paths_without_moving_external_file(
    tmp_db, tmp_path, unsafe_field
):
    import ledger_store
    from services.generation_recovery_service import GenerationRecoveryService

    output_dir = tmp_path / 'runtime' / 'output'
    staging_dir = output_dir / '.staging'
    output_dir.mkdir(parents=True)
    staging_dir.mkdir()
    external = tmp_path / 'outside' / f'{unsafe_field}.docx'
    external.parent.mkdir()
    external.write_bytes(b'outside-data-must-remain')
    paths = {
        'output_path': output_dir / 'safe.docx',
        'staging_path': staging_dir / 'safe.stage.docx',
    }
    paths[unsafe_field] = external
    job_id = f'unsafe-{unsafe_field}'
    ledger_store.create_generation_job(
        job_id, str(paths['output_path']), str(paths['staging_path'])
    )

    report = GenerationRecoveryService(
        ledger_store=ledger_store,
        output_dir=output_dir,
        staging_dir=staging_dir,
        additional_staging_dirs=(),
    ).reconcile()

    assert report['attention'] == 1
    assert external.read_bytes() == b'outside-data-must-remain'
    assert not (output_dir / '.recovery').exists()
    job = ledger_store.get_generation_job(job_id)
    assert job['state'] == 'attention'
    assert job['recovery_action'] == 'rejected_unsafe_generation_paths'


def test_recovery_sanitizes_journal_job_id_before_building_isolation_target(
    tmp_db, tmp_path
):
    import ledger_store
    from services.generation_recovery_service import GenerationRecoveryService

    output_dir = tmp_path / 'runtime' / 'output'
    staging_dir = output_dir / '.staging'
    staging_dir.mkdir(parents=True)
    generated = output_dir / 'generated.docx'
    generated.write_bytes(b'uncommitted')
    ledger_store.create_generation_job(
        '../../escape', str(generated), str(staging_dir / 'missing.docx')
    )

    report = GenerationRecoveryService(
        ledger_store=ledger_store,
        output_dir=output_dir,
        staging_dir=staging_dir,
        additional_staging_dirs=(),
    ).reconcile()

    assert report['recovered'] == 1
    recovery_files = list((output_dir / '.recovery').iterdir())
    assert len(recovery_files) == 1
    assert recovery_files[0].read_bytes() == b'uncommitted'
    assert '..' not in recovery_files[0].name
    assert not (tmp_path / 'escape-final-generated.docx').exists()


@pytest.mark.parametrize('final_status', ['contract_created', 'archived'])
def test_final_procurement_project_rejects_implicit_negotiation_reopen(
    tmp_db, final_status
):
    import ledger_store
    import procurement_store

    procurement_store.init_db()
    project_id = procurement_store.create_project({
        'project_no': f'P1-{final_status}',
        'project_name': '采购终态回归',
    })
    with ledger_store.get_conn() as conn:
        conn.execute(
            'UPDATE procurement_projects SET status = ? WHERE id = ?',
            (final_status, project_id),
        )

    with pytest.raises(ValueError, match='不能自动变更'):
        procurement_store.save_negotiation_round(
            project_id, 1, '2026-08-11', '不应写入', []
        )

    assert procurement_store.get_project(project_id)['status'] == final_status
    assert procurement_store.list_negotiation_rounds(project_id) == []
