"""Register external contract import HTTP adapters."""

from flask import Blueprint

from routes.contract_import_confirmation_routes import (
    register_contract_import_confirmation_routes,
)
from routes.contract_import_upload_routes import (
    register_contract_import_upload_routes,
)


def register(app):
    bp = Blueprint('contract_import', __name__)
    register_contract_import_upload_routes(bp)
    register_contract_import_confirmation_routes(bp)
    app.register_blueprint(bp)
