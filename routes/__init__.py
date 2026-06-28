"""Route registration helpers for the contract generation tool."""

from routes.settings_bp import register as register_settings
from routes.templates_bp import register as register_templates
from routes.contracts_bp import register as register_contracts
from routes.payments_bp import register as register_payments
from routes.excel_bill_bp import register as register_excel_bill
from routes.procurement_bp import register as register_procurement


def register_all(app):
    """Register all routes on the Flask app."""
    register_settings(app)
    register_templates(app)
    register_contracts(app)
    register_payments(app)
    register_excel_bill(app)
    register_procurement(app)
