"""Application services for template history and restoration."""

from __future__ import annotations

import json

import template_def
from utils.logger import get_logger


TEMPLATE_SUFFIX = '.contract-template'


def canonical_template_name(name):
    if name.endswith(TEMPLATE_SUFFIX):
        return name[:-len(TEMPLATE_SUFFIX)]
    return name


def list_versions_with_comparisons(name):
    template_name = canonical_template_name(name)
    versions = template_def.list_versions(template_name)
    for version in versions:
        try:
            version['comparison'] = template_def.compare_version(
                template_name,
                version['filename'],
            )
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            get_logger().warning(
                'Failed to compare template version %s/%s',
                template_name,
                version['filename'],
                exc_info=True,
            )
            version['comparison'] = None
    return template_name, versions


def restore_template_version(name, version_filename):
    template_def.restore_version(
        canonical_template_name(name),
        version_filename,
    )
