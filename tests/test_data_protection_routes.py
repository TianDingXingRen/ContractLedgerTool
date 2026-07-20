from services import data_protection_service


def _csrf(client):
    with client.session_transaction() as session:
        session['_csrf_token'] = 'protection-token'
    return 'protection-token'


def test_enable_data_protection_requires_recovery_acknowledgement(app, client):
    response = client.post(
        '/data-protection/enable',
        data={'csrf_token': _csrf(client)},
        headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_enable_data_protection_returns_report(app, client, monkeypatch):
    monkeypatch.setattr(data_protection_service, 'enable_data_protection', lambda _paths: {
        'success': True,
        'encrypted': 12,
        'already_encrypted': 0,
        'errors': [],
        'status': {'enabled': True},
    })
    response = client.post(
        '/data-protection/enable',
        data={'csrf_token': _csrf(client), 'acknowledge_recovery': '1'},
        headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 200
    assert response.get_json()['report']['encrypted'] == 12


def test_enable_data_protection_reports_partial_failure(app, client, monkeypatch):
    monkeypatch.setattr(data_protection_service, 'enable_data_protection', lambda _paths: {
        'success': False,
        'encrypted': 3,
        'already_encrypted': 1,
        'errors': ['database busy'],
        'status': {'partial': True},
    })
    response = client.post(
        '/data-protection/enable',
        data={'csrf_token': _csrf(client), 'acknowledge_recovery': '1'},
        headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 400
    assert response.get_json()['report']['errors'] == ['database busy']


def test_diagnostics_includes_data_protection_status(app, client, monkeypatch):
    monkeypatch.setattr(data_protection_service, 'data_protection_status', lambda _paths: {
        'supported': True,
        'enabled': False,
        'partial': False,
        'description': 'not enabled',
        'warning': 'backup key',
    })
    response = client.get('/api/diagnostics')
    assert response.status_code == 200
    assert response.get_json()['data_protection']['supported'] is True


def test_diagnostics_reports_effective_bind_address(app, client):
    app.config['CONTRACT_TOOL_BIND_HOST'] = '127.0.0.1'
    app.config['CONTRACT_TOOL_BIND_PORT'] = 51234
    response = client.get('/api/diagnostics')
    assert response.status_code == 200
    assert response.get_json()['app']['host'] == '127.0.0.1'
    assert response.get_json()['app']['port'] == 51234
