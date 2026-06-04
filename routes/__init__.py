"""Route registration helpers for the contract generation tool."""

from routes.settings_bp import register as register_settings
from routes.templates_bp import register as register_templates
from routes.contracts_bp import register as register_contracts
from routes.payments_bp import register as register_payments


def register_all(app):
    """Register all routes on the Flask app."""
    register_settings(app)
    register_templates(app)
    register_contracts(app)
    register_payments(app)
