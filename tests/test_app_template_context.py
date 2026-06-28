def _merged_template_context(app):
    merged = {}
    for processor in app.template_context_processors[None]:
        merged.update(processor())
    return merged


def test_template_context_includes_shared_labels_and_csrf(app):
    from utils import helpers

    with app.test_request_context('/'):
        context = _merged_template_context(app)

    assert context['contract_status_labels'] is helpers.CONTRACT_STATUS_LABELS
    assert context['procurement_stage_labels'] is helpers.PROCUREMENT_STAGE_LABELS
    assert context['quote_import_status_labels'] is helpers.QUOTE_IMPORT_STATUS_LABELS
    assert callable(context['csrf_token'])


def test_template_csrf_token_is_stable_within_session(app):
    with app.test_request_context('/'):
        context = _merged_template_context(app)
        first_token = context['csrf_token']()
        second_token = context['csrf_token']()

    assert first_token
    assert second_token == first_token


def test_csrf_token_reuses_existing_session_value(app):
    from core.app_template_context import csrf_token

    with app.test_request_context('/'):
        from flask import session

        session['_csrf_token'] = 'existing-token'

        assert csrf_token() == 'existing-token'
