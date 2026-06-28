"""Template context registration for shared labels and helpers."""

import uuid

from flask import session

from utils import helpers


def csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = uuid.uuid4().hex
        session['_csrf_token'] = token
    return token


def register_template_context(app, csrf_token_func=csrf_token):
    """Register shared template globals on a Flask app."""

    @app.context_processor
    def inject_label_maps():
        return {
            'contract_status_labels': helpers.CONTRACT_STATUS_LABELS,
            'confirm_status_labels': helpers.CONFIRM_STATUS_LABELS,
            'payment_status_labels': helpers.PAYMENT_STATUS_LABELS,
            'confidence_labels': helpers.CONFIDENCE_LABELS,
            'procurement_status_labels': helpers.PROCUREMENT_STATUS_LABELS,
            'procurement_method_labels': helpers.PROCUREMENT_METHOD_LABELS,
            'procurement_stage_labels': helpers.PROCUREMENT_STAGE_LABELS,
            'procurement_stage_status_labels': helpers.PROCUREMENT_STAGE_STATUS_LABELS,
            'clarification_status_labels': helpers.CLARIFICATION_STATUS_LABELS,
            'quote_status_labels': helpers.QUOTE_STATUS_LABELS,
            'quote_import_status_labels': helpers.QUOTE_IMPORT_STATUS_LABELS,
            'csrf_token': csrf_token_func,
        }
