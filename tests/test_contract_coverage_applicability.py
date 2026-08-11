import pytest

import ledger_store
from utils.contract_import_forms import summary_for_render, summary_from_form
from utils.generation_utils import parse_contract_classification


def _range(start=2, end=4):
    return {
        'title': '数字发次合同',
        'project_name': '试验项目',
        'coverage_mode': 'range',
        'coverage_start': start,
        'coverage_end': end,
    }


def test_coverage_mode_is_required_and_modes_are_mutually_exclusive():
    with pytest.raises(ValueError, match='填写数字范围.*不适用'):
        parse_contract_classification({})
    with pytest.raises(ValueError, match='必须同时填写'):
        parse_contract_classification({
            'coverage_mode': 'range',
            'project_name': '试验项目',
            'coverage_start': '1',
        })
    with pytest.raises(ValueError, match='项目名称'):
        parse_contract_classification({
            'coverage_mode': 'range',
            'coverage_start': '1',
            'coverage_end': '2',
        })
    with pytest.raises(ValueError, match='不能填写'):
        parse_contract_classification({
            'coverage_mode': 'not_applicable',
            'coverage_start': '1',
            'coverage_end': '2',
        })

    parsed = parse_contract_classification({
        'coverage_mode': 'not_applicable',
        'project_name': '',
    })
    assert parsed['coverage_not_applicable'] is True
    assert parsed['coverage_start'] is None
    assert parsed['coverage_end'] is None


def test_import_form_round_trips_coverage_mode():
    form = {
        'title': '服务合同',
        'status': 'draft',
        'coverage_mode': 'not_applicable',
    }
    summary = summary_from_form(form)
    assert summary['coverage_mode'] == 'not_applicable'
    assert summary['coverage_not_applicable'] is True
    rendered = summary_for_render(form)
    assert rendered['coverage_mode'] == 'not_applicable'
    assert rendered['coverage_not_applicable'] is True


def test_new_range_and_not_applicable_contracts_create_expected_serials(tmp_db):
    range_id = ledger_store.create_contract(_range(), {}, 'range.docx')
    range_contract = ledger_store.get_contract(range_id)
    assert range_contract['coverage_not_applicable'] == 0
    assert [row['serial_no'] for row in ledger_store.list_contract_serials(range_id)] == [
        2, 3, 4,
    ]

    not_applicable_id = ledger_store.create_contract({
        'title': '服务合同',
        'coverage_mode': 'not_applicable',
    }, {}, 'service.docx')
    not_applicable = ledger_store.get_contract(not_applicable_id)
    assert not_applicable['coverage_not_applicable'] == 1
    assert not_applicable['coverage_start'] is None
    assert not_applicable['coverage_end'] is None
    assert ledger_store.list_contract_serials(not_applicable_id) == []


def test_new_contract_rejects_conflicting_or_incomplete_coverage(tmp_db):
    with pytest.raises(ValueError, match='项目名称'):
        ledger_store.create_contract({
            **_range(), 'project_name': '',
        }, {}, 'missing-project.docx')
    with pytest.raises(ValueError, match='不能填写'):
        ledger_store.create_contract({
            **_range(), 'coverage_mode': 'not_applicable',
            'coverage_not_applicable': True,
        }, {}, 'conflict.docx')
    with pytest.raises(ValueError, match='请选择并填写'):
        ledger_store.create_contract({
            'title': '缺少范围', 'coverage_mode': 'range',
        }, {}, 'missing-range.docx')


def test_historical_pending_contract_locks_first_range_choice(tmp_db):
    contract_id = ledger_store.create_contract(
        {'title': '历史待补合同'}, {}, 'pending.docx'
    )
    pending = ledger_store.get_contract(contract_id)
    assert pending['coverage_not_applicable'] == 0
    assert pending['coverage_start'] is None

    ledger_store.update_contract(contract_id, {
        'project_name': '历史项目',
        'coverage_not_applicable': 0,
        'coverage_start': 5,
        'coverage_end': 6,
    })
    ledger_store.update_contract(contract_id, {
        'coverage_not_applicable': 0,
        'coverage_start': 4,
        'coverage_end': 7,
    })
    updated = ledger_store.get_contract(contract_id)
    assert (updated['coverage_start'], updated['coverage_end']) == (4, 7)
    assert [row['serial_no'] for row in ledger_store.list_contract_serials(contract_id)] == [
        4, 5, 6, 7,
    ]

    with pytest.raises(ValueError, match='不能改为不适用'):
        ledger_store.update_contract(contract_id, {
            'coverage_not_applicable': 1,
            'coverage_start': None,
            'coverage_end': None,
        })
    unchanged = ledger_store.get_contract(contract_id)
    assert (unchanged['coverage_start'], unchanged['coverage_end']) == (4, 7)


def test_historical_pending_contract_locks_not_applicable_and_keeps_serial_data(
    tmp_db,
):
    contract_id = ledger_store.create_contract(
        {'title': '历史服务合同'}, {}, 'pending-service.docx'
    )
    with ledger_store.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO contract_serials
                (contract_id, serial_no, amount_minor, status, remark,
                 created_at, updated_at)
            VALUES (?, 9, 12300, 'active', '历史备注', ?, ?)
            """,
            (contract_id, '2026-01-01', '2026-01-01'),
        )

    ledger_store.update_contract(contract_id, {
        'coverage_not_applicable': 1,
        'coverage_start': None,
        'coverage_end': None,
    })
    contract = ledger_store.get_contract(contract_id)
    assert contract['coverage_not_applicable'] == 1
    serial = ledger_store.list_contract_serials(
        contract_id, include_inactive=True
    )[0]
    assert serial['status'] == 'inactive'
    assert serial['amount_minor'] == 12300
    assert serial['remark'] == '历史备注'

    with pytest.raises(ValueError, match='不能改为数字范围'):
        ledger_store.update_contract(contract_id, {
            'project_name': '项目',
            'coverage_not_applicable': 0,
            'coverage_start': 1,
            'coverage_end': 2,
    })
    assert ledger_store.get_contract(contract_id)['coverage_not_applicable'] == 1


def test_not_applicable_transition_preserves_historical_payment_serial_link(tmp_db):
    contract_id = ledger_store.create_contract(
        {'title': '历史付款关联'}, {}, 'historical-plan.docx'
    )
    with ledger_store.get_conn() as conn:
        serial_id = conn.execute(
            """
            INSERT INTO contract_serials
                (contract_id, serial_no, status, created_at, updated_at)
            VALUES (?, 9, 'active', ?, ?)
            """,
            (contract_id, '2026-01-01', '2026-01-01'),
        ).lastrowid

    plan_id = ledger_store.insert_payment_plan(contract_id, {
        'contract_serial_id': serial_id,
        'phase_name': '历史节点',
        'due_amount': 100,
    })
    ledger_store.update_contract(contract_id, {
        'coverage_not_applicable': 1,
        'coverage_start': None,
        'coverage_end': None,
    })

    preserved = ledger_store.get_payment_plan(plan_id)
    assert preserved['contract_serial_id'] == serial_id
    assert preserved['serial_status'] == 'inactive'

    ledger_store.save_payment_plan_changes(contract_id, [{
        'id': plan_id,
        'data': {
            'contract_serial_id': serial_id,
            'remark': '保留历史发次关联',
        },
    }])
    edited = ledger_store.get_payment_plan(plan_id)
    assert edited['contract_serial_id'] == serial_id
    assert edited['remark'] == '保留历史发次关联'
