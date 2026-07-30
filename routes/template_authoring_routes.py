"""HTTP adapters for uploading and creating templates."""

from __future__ import annotations

import json

from flask import redirect, render_template, request, session, url_for

from services import template_authoring_service
from utils.errors import safe_parse_error
from utils.logger import get_logger
from utils.template_forms import parse_template_fields


def register_template_authoring_routes(bp):
    @bp.get('/create-template')
    def create_template():
        style_sid = request.args.get('style_sid')
        if not style_sid:
            style_sid = session.pop('style_sid', None)
        context = {
            'stored_name': '',
            'raw_name': '',
            'detected_fields': [],
        }
        if style_sid:
            try:
                context = (
                    template_authoring_service.load_style_context(
                        style_sid
                    )
                )
            except (FileNotFoundError, json.JSONDecodeError):
                get_logger().info(
                    '模板样式会话已失效',
                    exc_info=True,
                )
        return render_template('create_template.html', **context)

    @bp.post('/template/upload-style')
    def upload_style():
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return '未选择文件', 400
        try:
            style_sid = (
                template_authoring_service.upload_template_style(
                    upload.stream,
                    upload.filename,
                )
            )
        except template_authoring_service.TemplateUploadRejected as exc:
            return str(exc), 400
        except (
            template_authoring_service.TemplateMarkerDetectionFailed
        ) as exc:
            return safe_parse_error(
                exc.cause,
                'DOCX占位符解析失败',
                500,
            )
        session['style_sid'] = style_sid
        return redirect(url_for('templates.create_template'))

    @bp.post('/template/manual-save')
    def template_manual_save():
        try:
            fields = parse_template_fields(request.form)
            result = (
                template_authoring_service.create_manual_template(
                    request.form.get('template_name', ''),
                    request.form.get('template_category', ''),
                    request.form.get('stored_name', ''),
                    fields,
                )
            )
        except ValueError as exc:
            return str(exc), 400
        session['sid'] = result.session_id
        return redirect(
            url_for(
                'templates.template_editor',
                name=result.filename,
            )
        )
