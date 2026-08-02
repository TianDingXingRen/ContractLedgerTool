"""Register payment-plan HTTP adapters."""

from datetime import date

from flask import Blueprint

from routes.payment_contract_routes import register_contract_payment_routes
from routes.payment_export_routes import register_payment_export_routes
from routes.payment_plan_routes import register_payment_plan_routes


def _today():
    """Late-bound clock retained for deterministic route tests."""
    return date.today()


def register(app):
    bp = Blueprint('payments', __name__)
    register_contract_payment_routes(bp)
    register_payment_plan_routes(bp, _today)
    register_payment_export_routes(bp)
    app.register_blueprint(bp)
