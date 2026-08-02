"""Register contract-item and production-notice HTTP adapters."""

from flask import Blueprint

from routes.contract_item_routes import register_contract_item_routes
from routes.production_notice_action_routes import (
    register_production_notice_action_routes,
)
from routes.production_notice_routes import (
    register_production_notice_routes,
)


def register(app):
    bp = Blueprint('production', __name__)
    register_contract_item_routes(bp)
    register_production_notice_routes(bp)
    register_production_notice_action_routes(bp)
    app.register_blueprint(bp)
