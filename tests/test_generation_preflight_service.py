from types import SimpleNamespace

from services import generation_preflight_service as preflight


def _template(name='测试模板'):
    return SimpleNamespace(name=name)


def test_single_preflight_reports_duplicate_and_missing_summary(monkeypatch):
    monkeypatch.setattr(preflight, 'infer_contract_summary', lambda *_: {
        'contract_no': 'DUP-001',
        'counterparty': '',
        'amount': None,
        'sign_date': '',
    })
    monkeypatch.setattr(preflight.ledger_store, 'contract_no_exists', lambda value: value == 'DUP-001')

    result = preflight.build_single_preflight(
        _template(), [], {}, {
            'project_name': '',
            'coverage_mode': 'not_applicable',
            'coverage_not_applicable': True,
            'coverage_start': None,
            'coverage_end': None,
        },
    )

    assert result['ok'] is False
    assert result['mode'] == 'single'
    assert len(result['blocking']) == 1
    assert len(result['warnings']) == 3
    assert result['summary']['contract_no'] == 'DUP-001'
    assert result['summary']['coverage_mode'] == 'not_applicable'
    assert result['summary']['coverage_not_applicable'] is True


def test_batch_preflight_validates_counterparties_fields_and_duplicates(monkeypatch):
    monkeypatch.setattr(
        preflight,
        'contract_number_keys',
        lambda _fields: ['contract_no'],
    )
    monkeypatch.setattr(
        preflight.ledger_store,
        'contract_no_exists',
        lambda value: value in {'BATCH-001-002', 'BATCH-001-006'},
    )

    missing = preflight.build_batch_preflight(
        _template(), [], {}, {}, [], [],
    )
    assert missing['ok'] is False
    assert len(missing['blocking']) == 2

    result = preflight.build_batch_preflight(
        _template(), [], {'contract_no': 'BATCH-001'},
        {
            'project_name': '批量项目', 'coverage_mode': 'range',
            'coverage_not_applicable': False,
            'coverage_start': 1, 'coverage_end': 6,
        },
        [f'供应商{i}' for i in range(1, 7)], ['counterparty'],
    )

    assert result['ok'] is False
    assert len(result['blocking']) == 1
    assert 'BATCH-001-002' in result['blocking'][0]
    assert result['summary']['count'] == 6
    assert len(result['summary']['counterparties_preview']) == 5
    assert result['summary']['coverage_mode'] == 'range'


def test_batch_preflight_without_contract_number_field(monkeypatch):
    monkeypatch.setattr(
        preflight,
        'contract_number_keys',
        lambda _fields: [],
    )
    result = preflight.build_batch_preflight(
        _template(), [], {}, {}, ['供应商'], ['counterparty'],
    )
    assert result['ok'] is True
    assert result['blocking'] == []
