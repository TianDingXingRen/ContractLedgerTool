"""Template context registration for shared labels and helpers."""

import os
import uuid
from decimal import Decimal, InvalidOperation

from flask import session, url_for
from werkzeug.utils import safe_join

from utils import labels


def csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = uuid.uuid4().hex
        session['_csrf_token'] = token
    return token


def register_template_context(app, csrf_token_func=csrf_token):
    """Register shared template globals on a Flask app."""

    def static_url(filename):
        """Return a cache-busted URL for a packaged static asset."""
        path = safe_join(app.static_folder, filename)
        if path is None:
            raise ValueError('静态资源路径无效')
        try:
            stat = os.stat(path)
            version = f'{stat.st_mtime_ns:x}-{stat.st_size:x}'
        except OSError:
            version = 'missing'
        return url_for('static', filename=filename, v=version)

    def format_money(value, empty='—'):
        if value is None or value == '':
            return empty
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return empty
        return f'¥{amount:,.2f}'

    def format_date(value, empty='—'):
        text = str(value or '').strip()
        if not text:
            return empty
        return text[:10] if len(text) >= 10 else text

    def ui_tone(value):
        return {
            'active': 'blue', 'signed': 'blue', 'issued': 'blue',
            'acknowledged': 'blue', 'confirmed': 'blue', 'exact': 'green',
            'completed': 'green', 'closed': 'green', 'paid': 'green',
            'verified': 'green', 'valid': 'green', 'partial': 'orange',
            'pending': 'orange', 'unpaid': 'orange', 'draft': 'gray',
            'void': 'gray', 'cancelled': 'gray', 'manual': 'gray',
            'conflict': 'red', 'unsupported': 'red', 'exception': 'red',
            'red': 'red', 'overdue': 'red',
        }.get(str(value or '').strip(), 'gray')

    @app.context_processor
    def inject_label_maps():
        return {
            'contract_status_labels': labels.CONTRACT_STATUS_LABELS,
            'confirm_status_labels': labels.CONFIRM_STATUS_LABELS,
            'payment_status_labels': labels.PAYMENT_STATUS_LABELS,
            'confidence_labels': labels.CONFIDENCE_LABELS,
            'payment_parse_status_labels': labels.PAYMENT_PARSE_STATUS_LABELS,
            'payment_reason_labels': labels.PAYMENT_REASON_LABELS,
            'payment_amount_basis_labels': labels.PAYMENT_AMOUNT_BASIS_LABELS,
            'procurement_status_labels': labels.PROCUREMENT_STATUS_LABELS,
            'procurement_method_labels': labels.PROCUREMENT_METHOD_LABELS,
            'procurement_stage_labels': labels.PROCUREMENT_STAGE_LABELS,
            'procurement_stage_status_labels': labels.PROCUREMENT_STAGE_STATUS_LABELS,
            'clarification_status_labels': labels.CLARIFICATION_STATUS_LABELS,
            'quote_status_labels': labels.QUOTE_STATUS_LABELS,
            'quote_import_status_labels': labels.QUOTE_IMPORT_STATUS_LABELS,
            'csrf_token': csrf_token_func,
            'static_url': static_url,
            'format_money': format_money,
            'format_date': format_date,
            'ui_tone': ui_tone,
        }
