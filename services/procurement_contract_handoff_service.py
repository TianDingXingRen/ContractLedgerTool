"""Application service for procurement-to-contract editor handoff."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from services import award_service, procurement_project_service
from utils.session_store import save_session_data


@dataclass(frozen=True)
class ProcurementEditorSession:
    session_id: str


def create_award_editor_session(
    project_id,
    template_filename,
    paths,
):
    filename = os.path.basename(str(template_filename or ''))
    data = award_service.prepare_editor_session(
        project_id,
        filename,
        paths,
    )
    return _save_editor_session(data, paths)


def create_direct_editor_session(
    project_id,
    template_filename,
    paths,
):
    filename = os.path.basename(str(template_filename or ''))
    data = (
        procurement_project_service.prepare_direct_contract_session(
            project_id,
            filename,
            paths,
        )
    )
    return _save_editor_session(data, paths)


def _save_editor_session(data, paths):
    session_id = uuid.uuid4().hex
    save_session_data(session_id, data, paths)
    return ProcurementEditorSession(session_id=session_id)
