"""HTTP adapters for browsing, editing, and previewing templates."""

from __future__ import annotations

from flask import (
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from services import template_catalog_service
from utils.errors import safe_error


def register_template_catalog_routes(bp):
    @bp.get('/templates')
    def list_templates():
        templates = (
            template_catalog_service.list_template_summaries(
                request.args.get('category', '')
            )
        )
        return render_template('list.html', templates=templates)

    @bp.get('/template/<name>')
    def template_editor(name):
        try:
            view = template_catalog_service.open_template_editor(
                name
            )
        except ValueError as exc:
            return str(exc), 400
        except template_catalog_service.TemplateFileMissing as exc:
            return str(exc), 404
        except template_catalog_service.TemplateLoadFailed as exc:
            return safe_error(
                exc.cause,
                '加载模板失败',
                500,
            )
        session['sid'] = view.session_id
        return render_template(
            'editor.html',
            fields=view.fields,
            field_count=len(view.fields),
            template_name=view.template_name,
            template_filename=view.template_filename,
            template_revision=view.template_revision,
            draft_scope=view.draft_scope,
            preview_blocks=view.preview_blocks,
            preview_warnings=view.preview_warnings,
            project_names=view.project_names,
            classification_project_name='',
            classification_subsystem_name='',
            batch_allowed=True,
        )

    @bp.post('/template/<name>/preview')
    def template_preview(name):
        if not name or name in {'None', '未命名'}:
            return '模板名称无效，请先保存模板', 400
        try:
            artifact = (
                template_catalog_service.generate_template_preview(
                    name,
                    request.form,
                )
            )
        except template_catalog_service.TemplateFileMissing as exc:
            return str(exc), 404
        except template_catalog_service.TemplateLoadFailed as exc:
            return safe_error(
                exc.cause,
                '加载模板失败',
                500,
            )
        except (
            template_catalog_service.TemplateSourcePathRejected
        ) as exc:
            return safe_error(exc.cause, '模板路径无效')
        except template_catalog_service.TemplatePreviewRejected as exc:
            return str(exc), 400
        except (
            template_catalog_service.TemplatePreviewGenerationFailed
        ) as exc:
            return str(exc), 500
        except ValueError as exc:
            return str(exc), 400
        return send_file(
            artifact.path,
            as_attachment=True,
            download_name=artifact.download_name,
            mimetype=artifact.mimetype,
        )

    @bp.post('/template/<filename>/delete')
    def template_delete(filename):
        template_catalog_service.delete_template(filename)
        return redirect(url_for('templates.list_templates'))

    @bp.post('/template/<filename>/copy')
    def template_copy(filename):
        new_filename = (
            template_catalog_service.copy_template(filename)
        )
        if not new_filename:
            return '复制模板失败', 500
        return redirect(url_for('templates.list_templates'))
