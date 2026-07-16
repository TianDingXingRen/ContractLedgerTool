import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import ledger_store
import procurement_store
from core.domain_errors import ProcurementLinkError
from services.contract_generation_service import (
    ContractGenerationRequest,
    ContractGenerationService,
    ProcurementLink,
)
from services.generation_recovery_service import GenerationRecoveryService


class SimulatedProcessTermination(BaseException):
    pass


def _only_job():
    with ledger_store.get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM contract_generation_jobs ORDER BY created_at, job_id'
        ).fetchall()
    assert len(rows) == 1
    return dict(rows[0])


def _template():
    return SimpleNamespace(name='事务测试模板', data={
        'template_name': '事务测试模板',
        'fields': [
            {'id': 0, 'key': 'counterparty', 'label': '对方单位', 'field_type': 'text'},
        ],
    })


def _request(path, link=None):
    tpl = _template()
    return ContractGenerationRequest(
        template=tpl,
        fields=tpl.data['fields'],
        field_values={'counterparty': '测试供应商'},
        source_docx='',
        output_path=str(path),
        link=link,
    )


def test_generation_commits_file_and_ledger_together(tmp_db, tmp_path):
    service = ContractGenerationService(
        ledger_store=ledger_store, procurement_store=procurement_store
    )
    output = tmp_path / 'output' / 'contract.docx'

    result = service.generate(_request(output))

    assert os.path.isfile(output)
    assert ledger_store.get_contract(result.contract_id)['docx_path'] == str(output)
    assert _only_job()['state'] == 'completed'


def test_file_finalize_failure_rolls_back_ledger(tmp_db, tmp_path):
    def fail_replace(_source, _target):
        raise OSError('disk full')

    service = ContractGenerationService(
        ledger_store=ledger_store,
        procurement_store=procurement_store,
        replace_file=fail_replace,
    )
    output = tmp_path / 'output' / 'contract.docx'

    with pytest.raises(OSError, match='disk full'):
        service.generate(_request(output))

    assert ledger_store.list_contracts()['total'] == 0
    assert not output.exists()
    assert not list(output.parent.glob('*.stage-*'))
    assert _only_job()['state'] == 'failed'


def test_procurement_link_failure_rolls_back_file_and_ledger(
    tmp_db, tmp_path, monkeypatch
):
    procurement_store.init_db()
    service = ContractGenerationService(
        ledger_store=ledger_store, procurement_store=procurement_store
    )
    output = tmp_path / 'output' / 'contract.docx'
    monkeypatch.setattr(
        procurement_store, 'add_contract_ref',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('项目不存在')),
    )

    with pytest.raises(ProcurementLinkError):
        service.generate(_request(output, ProcurementLink(project_id=999)))

    assert ledger_store.list_contracts()['total'] == 0
    assert not output.exists()
    assert _only_job()['state'] == 'failed'


def test_recovery_isolates_file_moved_before_transaction_commit(tmp_db, tmp_path):
    def terminate_after_move(source, target):
        os.replace(source, target)
        raise SimulatedProcessTermination('power loss after file move')

    output_dir = tmp_path / 'output'
    output = output_dir / 'contract.docx'
    service = ContractGenerationService(
        ledger_store=ledger_store,
        procurement_store=procurement_store,
        replace_file=terminate_after_move,
        staging_dir=output_dir / '.staging',
    )

    with pytest.raises(SimulatedProcessTermination):
        service.generate(_request(output))

    assert output.is_file()
    assert ledger_store.list_contracts()['total'] == 0
    assert _only_job()['state'] == 'staged'

    recovery = GenerationRecoveryService(
        ledger_store=ledger_store,
        output_dir=output_dir,
    )
    report = recovery.reconcile()

    assert report['recovered'] == 1
    assert not output.exists()
    assert _only_job()['state'] == 'recovered'
    assert len(list((output_dir / '.recovery').iterdir())) == 1


def test_recovery_finalizes_commit_interrupted_before_terminal_marker(tmp_db, tmp_path):
    def terminate_after_commit(_result):
        raise SimulatedProcessTermination('power loss after database commit')

    output_dir = tmp_path / 'output'
    output = output_dir / 'contract.docx'
    service = ContractGenerationService(
        ledger_store=ledger_store,
        procurement_store=procurement_store,
        staging_dir=output_dir / '.staging',
        after_commit=terminate_after_commit,
    )

    with pytest.raises(SimulatedProcessTermination):
        service.generate(_request(output))

    job = _only_job()
    assert job['state'] == 'file_moved'
    assert ledger_store.get_contract(job['contract_id']) is not None
    assert output.is_file()

    recovery = GenerationRecoveryService(
        ledger_store=ledger_store,
        output_dir=output_dir,
    )
    report = recovery.reconcile()

    assert report['completed'] == 1
    assert _only_job()['state'] == 'completed'
    assert output.is_file()


def test_active_generation_job_reserves_output_name(tmp_db, tmp_path):
    output = tmp_path / 'output' / 'contract.docx'
    stage = tmp_path / 'output' / '.staging' / 'one.docx'
    ledger_store.create_generation_job('job-one', str(output), str(stage))

    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        ledger_store.create_generation_job(
            'job-two',
            str(output.with_name('CONTRACT.DOCX')),
            str(stage) + '.two',
        )

    assert 'UNIQUE constraint failed' in str(exc_info.value)


def test_recovery_isolates_untracked_staging_file(tmp_db, tmp_path):
    output_dir = tmp_path / 'output'
    staging = output_dir / '.staging' / 'orphan.docx'
    staging.parent.mkdir(parents=True)
    staging.write_bytes(b'orphan')
    recovery = GenerationRecoveryService(
        ledger_store=ledger_store,
        output_dir=output_dir,
    )

    report = recovery.reconcile()

    assert report['inspected'] == 0
    assert len(report['isolated_files']) == 1
    assert not staging.exists()
    assert Path(report['isolated_files'][0]).read_bytes() == b'orphan'
