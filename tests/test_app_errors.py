def test_404_error_handler_returns_json_for_api_clients(client):
    response = client.get('/missing-route', headers={'Accept': 'application/json'})

    assert response.status_code == 404
    assert response.get_json()['success'] is False
    assert 'not found' in response.get_json()['error'].lower()


def test_404_error_handler_renders_page_for_browser_clients(client):
    response = client.get('/missing-route')

    assert response.status_code == 404
    assert 'text/html' in response.content_type


def test_unhandled_error_handler_returns_generic_json(app, client):
    @app.route('/_test/unhandled-error')
    def _test_unhandled_error():
        raise RuntimeError('sensitive internal detail')

    response = client.get('/_test/unhandled-error', headers={'Accept': 'application/json'})

    assert response.status_code == 500
    assert response.get_json() == {'success': False, 'error': '服务器内部错误'}
