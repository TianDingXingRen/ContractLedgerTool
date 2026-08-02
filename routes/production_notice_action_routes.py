"""HTTP adapters for production notice state transitions."""

from __future__ import annotations

from flask import redirect, request, url_for

from core.domain_errors import NotFoundError
from services import production_commands


def _detail_redirect(notice_id, *, message='', error=''):
    params = {'notice_id': notice_id}
    if message:
        params['message'] = message
    if error:
        params['error'] = error
    return redirect(
        url_for(
            'production.production_notice_detail',
            **params,
        )
    )


def _transition(notice_id, action):
    try:
        message = production_commands.transition_production_notice(
            notice_id,
            action,
            operator=str(
                request.form.get('operator', '') or ''
            ).strip(),
            reason=str(
                request.form.get('reason', '') or ''
            ).strip(),
        )
    except NotFoundError as exc:
        return exc.public_message, exc.status_code
    except ValueError as exc:
        return _detail_redirect(notice_id, error=str(exc))
    return _detail_redirect(notice_id, message=message)


def register_production_notice_action_routes(bp):
    @bp.post('/production-notices/<int:notice_id>/issue')
    def production_notice_issue(notice_id):
        return _transition(notice_id, 'issue')

    @bp.post(
        '/production-notices/<int:notice_id>/acknowledge'
    )
    def production_notice_acknowledge(notice_id):
        return _transition(notice_id, 'acknowledge')

    @bp.post('/production-notices/<int:notice_id>/close')
    def production_notice_close(notice_id):
        return _transition(notice_id, 'close')

    @bp.post('/production-notices/<int:notice_id>/cancel')
    def production_notice_cancel(notice_id):
        return _transition(notice_id, 'cancel')

    @bp.post('/production-notices/<int:notice_id>/revise')
    def production_notice_revise(notice_id):
        operator = str(
            request.form.get('operator', '') or ''
        ).strip()
        try:
            new_id = production_commands.revise_production_notice(
                notice_id, operator
            )
        except NotFoundError as exc:
            return exc.public_message, exc.status_code
        except ValueError as exc:
            return _detail_redirect(notice_id, error=str(exc))
        return redirect(
            url_for(
                'production.production_notice_edit',
                notice_id=new_id,
            )
        )
