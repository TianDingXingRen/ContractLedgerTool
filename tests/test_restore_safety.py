import threading
import time

import pytest

import ledger_store
import procurement_store
from core.maintenance_gate import maintenance_gate
from services import handover_service


def test_restore_waits_for_active_request_before_replacing_database(tmp_db, monkeypatch):
    contract_id = ledger_store.create_contract({'title': 'backup value'}, {}, '')
    backup = ledger_store.create_backup('race_test')
    writer_ready = threading.Event()
    release_writer = threading.Event()
    restore_entered = threading.Event()
    restore_done = threading.Event()
    failures = []

    original_restore = ledger_store.backup_ops.restore_backup

    def observed_restore(*args, **kwargs):
        restore_entered.set()
        return original_restore(*args, **kwargs)

    monkeypatch.setattr(ledger_store.backup_ops, 'restore_backup', observed_restore)

    def writer():
        token, context_token = maintenance_gate.enter_request()
        try:
            with ledger_store.get_conn() as connection:
                connection.execute(
                    "UPDATE contracts SET title = 'concurrent value' WHERE id = ?",
                    (contract_id,),
                )
                writer_ready.set()
                assert release_writer.wait(5)
        except BaseException as exc:
            failures.append(exc)
        finally:
            maintenance_gate.leave_request(token, context_token)

    def restorer():
        try:
            ledger_store.restore_backup(backup['filename'])
        except BaseException as exc:
            failures.append(exc)
        finally:
            restore_done.set()

    writer_thread = threading.Thread(target=writer)
    restore_thread = threading.Thread(target=restorer)
    writer_thread.start()
    assert writer_ready.wait(5)
    restore_thread.start()
    time.sleep(0.2)
    assert not restore_entered.is_set()
    assert not restore_done.is_set()
    release_writer.set()
    writer_thread.join(5)
    restore_thread.join(5)

    assert not failures
    assert restore_entered.is_set()
    assert ledger_store.get_contract(contract_id)['title'] == 'backup value'


def test_restore_initialization_failure_rolls_back_previous_database(tmp_db, monkeypatch):
    ledger_store.create_contract({'title': 'backup value'}, {}, '')
    backup = ledger_store.create_backup('rollback_test')
    ledger_store.create_contract({'title': 'must survive failed restore'}, {}, '')
    original_init = ledger_store.init_db
    calls = 0

    def fail_first_init():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('simulated post-restore migration failure')
        return original_init()

    monkeypatch.setattr(ledger_store, 'init_db', fail_first_init)
    with pytest.raises(RuntimeError, match='simulated'):
        ledger_store.restore_backup(backup['filename'])

    assert calls == 2
    assert ledger_store.get_contract_stats()['total'] == 2


def test_full_restore_procurement_init_failure_rolls_back_everything(app, monkeypatch):
    ledger_store.create_contract({'title': 'package value'}, {}, '')
    package = handover_service.create_full_backup_package('failure_test')
    ledger_store.create_contract({'title': 'must survive failed full restore'}, {}, '')
    original_init = procurement_store.init_db
    calls = 0

    def fail_first_init():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('simulated procurement initialization failure')
        return original_init()

    monkeypatch.setattr(procurement_store, 'init_db', fail_first_init)
    with pytest.raises(RuntimeError, match='simulated procurement'):
        handover_service.restore_full_backup_package(package['filename'])

    assert calls == 2
    assert ledger_store.get_contract_stats()['total'] == 2
