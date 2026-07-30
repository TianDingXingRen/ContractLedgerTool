"""Template management blueprint composition."""

from flask import Blueprint

from routes.template_authoring_routes import (
    register_template_authoring_routes,
)
from routes.template_catalog_routes import (
    register_template_catalog_routes,
)
from routes.template_default_routes import (
    register_template_default_routes,
)
from routes.template_version_routes import (
    register_template_version_routes,
)


def register(app):
    bp = Blueprint('templates', __name__)
    register_template_authoring_routes(bp)
    register_template_catalog_routes(bp)
    register_template_version_routes(bp)
    register_template_default_routes(bp)
    app.register_blueprint(bp)
