import time

import pytest

import ledger_store
import procurement_store
from services.dashboard_service import build_dashboard_snapshot


def _seed_scale_data(contract_count=5_000, payment_count=20_000):
    now = '2026-07-16 00:00:00'
    with ledger_store.get_conn() as conn:
        conn.executemany(
            """INSERT INTO contracts
               (contract_no, title, counterparty, amount, amount_minor, sign_date,
                owner, status, project_name, deleted_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    f'PERF-{index}', f'Contract {index}', 'Supplier', 100.0, 10_000,
                    '2026-01-01', 'Owner', 'active', '', '', now, now,
                )
                for index in range(contract_count)
            ],
        )
        conn.executemany(
            """INSERT INTO payment_plans
               (contract_id, phase_name, payment_type, due_date, due_amount,
                due_amount_minor, paid_amount, paid_amount_minor, confirm_status,
                payment_status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    (index % contract_count) + 1, 'Payment', 'conditional',
                    '2026-07-20', 10.0, 1_000, 0.0, 0, 'confirmed', 'unpaid', now, now,
                )
                for index in range(payment_count)
            ],
        )


def test_dashboard_snapshot_reuses_one_sqlite_connection(tmp_db, monkeypatch):
    procurement_store.init_db()
    real_connect = ledger_store.sqlite3.connect
    calls = []

    def counting_connect(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get('database'))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(ledger_store.sqlite3, 'connect', counting_connect)
    build_dashboard_snapshot()
    assert len(calls) == 1


def test_high_frequency_queries_use_optimized_indexes(tmp_db):
    procurement_store.init_db()
    with ledger_store.get_conn() as conn:
        contract_id = conn.execute(
            """INSERT INTO contracts(title, docx_path, created_at, updated_at)
               VALUES ('Planner', '/planner.docx', '2026-07-16', '2026-07-16')"""
        ).lastrowid
        conn.executemany(
            """INSERT INTO payment_plans
               (contract_id, phase_name, confirm_status, payment_status, due_date,
                created_at, updated_at)
               VALUES (?, 'Plan', ?, 'unpaid', ?, '2026-07-16', '2026-07-16')""",
            [
                (contract_id, 'confirmed' if index < 10 else 'pending', '2026-07-20')
                for index in range(1_000)
            ],
        )
        # Empty/fresh SQLite databases do not have planner statistics yet and may
        # prefer the older, wider index.  Production maintenance runs ANALYZE;
        # mirror that state before asserting the intended scale query plan.
        conn.execute('ANALYZE')
        payment_plan = ' '.join(
            row['detail'] for row in conn.execute(
                """EXPLAIN QUERY PLAN
                   SELECT contract_id FROM payment_plans
                   WHERE confirm_status = 'confirmed' AND payment_status != 'paid'
                     AND due_date BETWEEN '2026-01-01' AND '2026-12-31'
                   ORDER BY due_date"""
            ).fetchall()
        )
        project_plan = ' '.join(
            row['detail'] for row in conn.execute(
                """EXPLAIN QUERY PLAN
                   SELECT id FROM procurement_projects
                   ORDER BY updated_at DESC, id DESC LIMIT 20"""
            ).fetchall()
        )
    assert 'idx_payment_actionable_due' in payment_plan
    assert 'idx_procurement_project_updated' in project_plan


@pytest.mark.slow
def test_dashboard_and_list_scale_targets(tmp_db):
    procurement_store.init_db()
    _seed_scale_data()

    started = time.perf_counter()
    snapshot = build_dashboard_snapshot()
    dashboard_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    result = ledger_store.list_contracts(page=1, per_page=20)
    list_elapsed = time.perf_counter() - started

    assert snapshot['contract_stats']['total'] == 5_000
    assert len(result['rows']) == 20
    assert dashboard_elapsed < 0.25
    assert list_elapsed < 0.15


@pytest.mark.slow
def test_large_dataset_performance_budget(tmp_db):
    procurement_store.init_db()
    _seed_scale_data(contract_count=10_000, payment_count=100_000)

    started = time.perf_counter()
    snapshot = build_dashboard_snapshot()
    dashboard_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    result = ledger_store.list_contracts(q='PERF-99', page=1, per_page=20)
    filtered_list_elapsed = time.perf_counter() - started

    assert snapshot['contract_stats']['total'] == 10_000
    assert result['total'] > 0
    # Budgets are intentionally tolerant of shared GitHub Windows runners while
    # still detecting accidental full-table Python processing.
    assert dashboard_elapsed < 2.0
    assert filtered_list_elapsed < 0.5
