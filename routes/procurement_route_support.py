"""Shared HTTP-only helpers for procurement route adapters."""

from __future__ import annotations

import logging
import os

from flask import abort, redirect, url_for

from services import procurement_project_service
from utils.errors import (
    GENERIC_ERROR,
    classified_error_message,
    log_form_error,
)
from utils.money import from_minor


_log = logging.getLogger('contract_tool')


def has_allowed_extension(filename, allowed_extensions):
    if not filename:
        return False
    extension = os.path.splitext(filename)[1].lower()
    return extension in allowed_extensions


def money(value):
    return from_minor(value)


def classified_procurement_error(error):
    return classified_error_message(error)


def project_or_404(project_id):
    project = procurement_project_service.get_project(project_id)
    if not project:
        abort(404, description='采购项目不存在')
    return project


def form_error(context, error):
    message, _ = log_form_error(
        context,
        error,
        logger=_log,
    )
    return message


def error_redirect(
    endpoint,
    error,
    exc_info=None,
    **values,
):
    message, is_system = classified_error_message(error)
    if is_system or (exc_info and message == GENERIC_ERROR):
        _log.error(
            '采购操作错误: %s',
            error,
            exc_info=exc_info,
        )
    elif exc_info:
        _log.info('采购操作错误: %s', error)
    values['error'] = message
    return redirect(url_for(endpoint, **values))


def stage_redirect_url(project_id, stage):
    endpoint = {
        'project': 'procurement.procurement_project_edit',
        'quotes': 'procurement.procurement_quote_import',
        'comparison': 'procurement.procurement_comparison',
        'negotiation': 'procurement.procurement_negotiation',
        'award': 'procurement.procurement_award',
        'contract': 'procurement.procurement_direct_contract',
    }.get(stage)
    if endpoint:
        return url_for(endpoint, project_id=project_id)
    if stage in {'items', 'suppliers', 'archive'}:
        anchor = {
            'items': 'items',
            'suppliers': 'suppliers',
            'archive': 'files',
        }[stage]
        return (
            url_for(
                'procurement.procurement_project_detail',
                project_id=project_id,
            )
            + f'#{anchor}'
        )
    return url_for(
        'procurement.procurement_project_detail',
        project_id=project_id,
    )


def project_section_url(project_id, section):
    return (
        url_for(
            'procurement.procurement_project_detail',
            project_id=project_id,
        )
        + f'#{section}'
    )
