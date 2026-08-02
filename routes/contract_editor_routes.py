"""Home dashboard and contract editor HTTP routes."""

from __future__ import annotations

import json
import os

from flask import redirect, render_template, request, session, url_for

from runtime.flask_paths import current_runtime_paths
from services import contract_editor_service, dashboard_service
from utils.session_store import load_session_data


def index():
    snapshot = dashboard_service.build_dashboard_snapshot()
    autostart = {'enabled': False, 'supported': os.name == 'nt'}
    return render_template(
        'index.html',
        **snapshot,
        autostart=autostart,
        autostart_error=request.args.get('autostart_error', ''),
    )


def editor():
    sid = session.get('sid')
    if not sid:
        return redirect(url_for('contracts.index'))

    try:
        data = load_session_data(sid, current_runtime_paths())
    except (FileNotFoundError, json.JSONDecodeError):
        return redirect(url_for('contracts.index'))

    model = contract_editor_service.build_editor_model(
        data,
        current_runtime_paths(),
    )
    return render_template('editor.html', **model)


def register_contract_editor_routes(bp):
    bp.add_url_rule('/', endpoint='index', view_func=index)
    bp.add_url_rule('/editor', endpoint='editor', view_func=editor)
