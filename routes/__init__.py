"""Route registration helpers for the contract generation tool."""

from routes.settings_bp import register as register_settings
from routes.templates_bp import register as register_templates
from routes.contracts_bp import register as register_contracts
from routes.contract_import_bp import register as register_contract_import
from routes.payments_bp import register as register_payments
from routes.excel_bill_bp import register as register_excel_bill
from routes.procurement_bp import register as register_procurement
from routes.production_bp import register as register_production
from routes.invoices_bp import register as register_invoices


def register_all(app):
    """Register all routes on the Flask app."""
    register_settings(app)
    register_templates(app)
    register_contracts(app)
    register_contract_import(app)
    register_payments(app)
    register_excel_bill(app)
    register_procurement(app)
    register_production(app)
    register_invoices(app)
