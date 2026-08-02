import pytest

from core.app_startup import should_open_browser, validate_bind_host


def test_should_not_open_browser_when_disabled():
    assert should_open_browser(
        no_browser=True,
        debug=False,
        environ={'WERKZEUG_RUN_MAIN': 'true'},
    ) is False


def test_should_open_browser_without_debug_even_before_reloader():
    assert should_open_browser(
        no_browser=False,
        debug=False,
        environ={},
    ) is True


def test_should_open_browser_in_debug_reloader_process():
    assert should_open_browser(
        no_browser=False,
        debug=True,
        environ={'WERKZEUG_RUN_MAIN': 'true'},
    ) is True


def test_should_wait_for_reloader_when_debugging():
    assert should_open_browser(
        no_browser=False,
        debug=True,
        environ={},
    ) is False


@pytest.mark.parametrize('host', ['127.0.0.1', '::1', 'localhost'])
def test_local_bind_hosts_are_allowed(host):
    assert validate_bind_host(host) == host


def test_remote_bind_requires_explicit_opt_in(tmp_path):
    certificate = tmp_path / 'server.crt'
    private_key = tmp_path / 'server.key'
    certificate.write_text('test certificate', encoding='utf-8')
    private_key.write_text('test key', encoding='utf-8')

    with pytest.raises(ValueError, match='CT_ALLOW_REMOTE'):
        validate_bind_host('0.0.0.0')
    with pytest.raises(ValueError, match='CT_REMOTE_ACCESS_TOKEN'):
        validate_bind_host('0.0.0.0', allow_remote=True)
    with pytest.raises(ValueError, match='CT_REMOTE_TLS_CERT'):
        validate_bind_host(
            '0.0.0.0', allow_remote=True,
            remote_token='0123456789abcdef',
        )
    assert validate_bind_host(
        '0.0.0.0',
        allow_remote=True,
        remote_token='0123456789abcdef',
        tls_cert=str(certificate),
        tls_key=str(private_key),
    ) == '0.0.0.0'
    with pytest.raises(ValueError, match='CT_DEBUG'):
        validate_bind_host(
            '0.0.0.0',
            allow_remote=True,
            remote_token='0123456789abcdef',
            tls_cert=str(certificate),
            tls_key=str(private_key),
            debug=True,
        )
