from types import SimpleNamespace

from services import generation_preflight_service as preflight


def _template(name='测试模板'):
    return SimpleNamespace(name=name)


def test_single_preflight_reports_duplicate_and_missing_summary(monkeypatch):
    monkeypatch.setattr(preflight.helpers, 'infer_contract_summary', lambda *_: {
        'contract_no': 'DUP-001',
        'counterparty': '',
        'amount': None,
        'sign_date': '',
    })
    monkeypatch.setattr(preflight.ledger_store, 'contract_no_exists', lambda value: value == 'DUP-001')

    result = preflight.build_single_preflight(
        _template(), [], {}, {'project_name': '试验项目'}, generate_pdf=False,
    )

    assert result['ok'] is False
    assert result['mode'] == 'single'
    assert len(result['blocking']) == 1
    assert len(result['warnings']) == 3
    assert result['summary']['contract_no'] == 'DUP-001'
    assert result['summary']['project_name'] == '试验项目'


def test_single_preflight_pdf_environment_warning(monkeypatch):
    monkeypatch.setattr(preflight.helpers, 'infer_contract_summary', lambda *_: {
        'contract_no': 'NEW-001',
        'counterparty': '供应商',
        'amount': 100.0,
        'sign_date': '2026-07-20',
    })
    monkeypatch.setattr(preflight.ledger_store, 'contract_no_exists', lambda _value: False)
    monkeypatch.setattr(preflight.pdf_exporter, 'diagnose_environment', lambda: {
        'winword_found': 'Not found', 'libreoffice_found': 'False',
    })

    result = preflight.build_single_preflight(_template(), [], {}, {}, generate_pdf=True)

    assert result['ok'] is True
    assert len(result['warnings']) == 1
    assert result['summary']['pdf'] is True


def test_single_preflight_has_no_pdf_warning_when_converter_exists(monkeypatch):
    monkeypatch.setattr(preflight.helpers, 'infer_contract_summary', lambda *_: {
        'contract_no': '',
        'counterparty': '供应商',
        'amount': 1,
        'sign_date': '2026-07-20',
    })
    monkeypatch.setattr(preflight.ledger_store, 'contract_no_exists', lambda _value: False)
    monkeypatch.setattr(preflight.pdf_exporter, 'diagnose_environment', lambda: {
        'winword_found': 'C:/Office/WINWORD.EXE', 'libreoffice_found': 'False',
    })

    result = preflight.build_single_preflight(_template(), [], {}, {}, generate_pdf=True)

    assert result['warnings'] == []


def test_batch_preflight_validates_counterparties_fields_and_duplicates(monkeypatch):
    monkeypatch.setattr(preflight.helpers, 'contract_number_keys', lambda _fields: ['contract_no'])
    monkeypatch.setattr(
        preflight.ledger_store,
        'contract_no_exists',
        lambda value: value in {'BATCH-001-002', 'BATCH-001-006'},
    )

    missing = preflight.build_batch_preflight(
        _template(), [], {}, {}, [], [], generate_pdf=False,
    )
    assert missing['ok'] is False
    assert len(missing['blocking']) == 2

    result = preflight.build_batch_preflight(
        _template(), [], {'contract_no': 'BATCH-001'},
        {'project_name': '批量项目', 'coverage_start': 1, 'coverage_end': 6},
        [f'供应商{i}' for i in range(1, 7)], ['counterparty'], generate_pdf=True,
    )

    assert result['ok'] is False
    assert len(result['blocking']) == 1
    assert 'BATCH-001-002' in result['blocking'][0]
    assert result['warnings']
    assert result['summary']['count'] == 6
    assert len(result['summary']['counterparties_preview']) == 5
    assert result['summary']['pdf'] is False


def test_batch_preflight_without_contract_number_field(monkeypatch):
    monkeypatch.setattr(preflight.helpers, 'contract_number_keys', lambda _fields: [])
    result = preflight.build_batch_preflight(
        _template(), [], {}, {}, ['供应商'], ['counterparty'], generate_pdf=False,
    )
    assert result['ok'] is True
    assert result['blocking'] == []
