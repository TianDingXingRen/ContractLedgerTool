"""HTTP adapters for template version history."""

from __future__ import annotations

from flask import redirect, render_template, url_for

from services import template_version_service
from utils.errors import safe_error


def register_template_version_routes(bp):
    @bp.get('/template/<name>/versions')
    def template_versions(name):
        template_name, versions = (
            template_version_service.list_versions_with_comparisons(
                name
            )
        )
        return render_template(
            'versions.html',
            template_name=template_name,
            versions=versions,
        )

    @bp.post(
        '/template/<name>/versions/'
        '<version_filename>/restore'
    )
    def template_version_restore(name, version_filename):
        try:
            template_version_service.restore_template_version(
                name,
                version_filename,
            )
        except FileNotFoundError as exc:
            return safe_error(
                exc,
                '版本文件不存在',
                404,
            )
        return redirect(url_for('templates.list_templates'))
