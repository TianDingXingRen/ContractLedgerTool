import logging

from utils.logger import (
    SensitiveDataFilter,
    get_request_id,
    reset_request_id,
    set_request_id,
)


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
