"""HTTP adapter for saving template default values."""

from __future__ import annotations

from flask import jsonify, request, session

from services import template_defaults_service
from utils.errors import GENERIC_TEMPLATE_ERROR


def register_template_default_routes(bp):
    @bp.post('/template-defaults')
    def save_template_defaults():
        session_id = session.get('sid')
        if not session_id:
            return jsonify(
                {'success': False, 'message': '未选择模板'}
            ), 400
        try:
            result = (
                template_defaults_service.save_template_defaults(
                    session_id,
                    request.form,
                )
            )
        except (
            template_defaults_service.TemplateDefaultsSessionExpired
        ) as exc:
            return jsonify(
                {'success': False, 'message': str(exc)}
            ), 400
        except (
            template_defaults_service.TemplateDefaultsFileMissing
        ) as exc:
            return jsonify(
                {'success': False, 'message': str(exc)}
            ), 404
        except (
            template_defaults_service.TemplateDefaultsRejected
        ) as exc:
            return jsonify(
                {'success': False, 'message': str(exc)}
            ), 400
        except (
            template_defaults_service.TemplateDefaultsOperationFailed
        ):
            return jsonify(
                {
                    'success': False,
                    'message': GENERIC_TEMPLATE_ERROR,
                }
            ), 500
        return jsonify(
            {
                'success': True,
                'message': '预制内容已保存到模板',
                'warnings': result.warnings,
            }
        )
