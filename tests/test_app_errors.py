import io


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


def test_http_exception_preserves_method_not_allowed_status(client):
    response = client.get('/reset')

    assert response.status_code == 405
    assert 'text/html' in response.content_type


def test_oversized_upload_preserves_request_too_large_status(app, client):
    app.config['MAX_CONTENT_LENGTH'] = 256
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'size-token'

    response = client.post(
        '/template/upload-style',
        data={
            'csrf_token': 'size-token',
            'file': (io.BytesIO(b'x' * 1024), 'large.docx'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 413
