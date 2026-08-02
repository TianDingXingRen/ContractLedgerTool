"""Composition root for contract generation and ledger routes."""

from flask import Blueprint

from routes.contract_batch_generation_routes import (
    register_contract_batch_generation_routes,
)
from routes.contract_download_routes import register_contract_download_routes
from routes.contract_editor_routes import register_contract_editor_routes
from routes.contract_generation_routes import register_contract_generation_routes
from routes.contract_ledger_routes import register_contract_ledger_routes
from routes.contract_workspace import register_contract_workspace


def register(app):
    bp = Blueprint('contracts', __name__)
    register_contract_editor_routes(bp)
    register_contract_generation_routes(bp)
    register_contract_batch_generation_routes(bp)
    register_contract_ledger_routes(bp)
    register_contract_workspace(bp)
    register_contract_download_routes(bp)
    app.register_blueprint(bp)
