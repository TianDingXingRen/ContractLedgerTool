import logging

import utils.logger as logger_module
from utils.logger import (
    SensitiveDataFilter,
    close_logging,
    get_request_id,
    reset_request_id,
    set_request_id,
)


def test_windowed_runtime_uses_file_logging_without_stdout(tmp_path, monkeypatch):
    close_logging()
    monkeypatch.setattr(logger_module.sys, 'stdout', None)
    try:
        logger = logger_module.setup_logging(str(tmp_path))
        assert len(logger.handlers) == 1
        logger.warning('background-service-warning')
        assert 'background-service-warning' in (
            tmp_path / 'app.log'
        ).read_text(encoding='utf-8')
    finally:
        close_logging()


def test_sensitive_filter_redacts_formatted_arguments():
    record = logging.LogRecord(
        'contract_tool', logging.INFO, __file__, 1,
        'account_no=%s token=%s', ('6222021234567890', 'secret-value'), None,
    )

    assert SensitiveDataFilter().filter(record)

    assert record.getMessage() == 'account_no=*** token=***'


def test_request_id_context_is_restored():
    before = get_request_id()
    token = set_request_id('request-42')
    try:
        assert get_request_id() == 'request-42'
    finally:
        reset_request_id(token)
    assert get_request_id() == before


def test_response_echoes_valid_request_id(client):
    response = client.get('/', headers={'X-Request-ID': 'trace-12345678'})
    try:
        assert response.headers['X-Request-ID'] == 'trace-12345678'
    finally:
        response.close()


def test_response_replaces_invalid_request_id(client):
    response = client.get('/', headers={'X-Request-ID': 'bad value'})
    try:
        generated = response.headers['X-Request-ID']
        assert len(generated) == 32
        int(generated, 16)
    finally:
        response.close()
