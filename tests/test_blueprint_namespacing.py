def test_all_application_endpoints_use_blueprint_namespaces(app):
    endpoints = {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.endpoint != 'static'
    }

    assert endpoints
    assert all('.' in endpoint for endpoint in endpoints)
    assert {endpoint.split('.', 1)[0] for endpoint in endpoints} == {
        'contract_import',
        'contracts',
        'excel_bill',
        'invoices',
        'payments',
        'procurement',
        'production',
        'settings',
        'templates',
    }


def test_core_navigation_renders_with_namespaced_endpoints(client):
    for path in ('/', '/templates', '/contracts', '/procurement/projects'):
        response = client.get(path)
        assert response.status_code == 200, path
