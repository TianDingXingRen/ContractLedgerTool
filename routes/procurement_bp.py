"""Procurement blueprint composition."""

from flask import Blueprint

from routes.procurement_contract_routes import (
    register_procurement_contract_routes,
)
from routes.procurement_decision_routes import (
    register_procurement_decision_routes,
)
from routes.procurement_document_routes import (
    register_document_routes,
)
from routes.procurement_import_routes import (
    register_procurement_import_routes,
)
from routes.procurement_item_supplier_routes import (
    register_procurement_item_supplier_routes,
)
from routes.procurement_project_routes import (
    register_procurement_project_routes,
)
from routes.procurement_quote_routes import (
    register_quote_management_routes,
)
from routes.procurement_route_support import (
    classified_procurement_error as _classified_error_message,
    error_redirect,
    form_error,
    money,
)

__all__ = ['_classified_error_message', 'register']


def register(app):
    bp = Blueprint('procurement', __name__)
    register_document_routes(bp, error_redirect)
    register_quote_management_routes(
        bp,
        error_redirect,
        form_error,
        money,
    )
    register_procurement_project_routes(bp)
    register_procurement_item_supplier_routes(bp)
    register_procurement_import_routes(bp)
    register_procurement_decision_routes(bp)
    register_procurement_contract_routes(bp)
    app.register_blueprint(bp)
