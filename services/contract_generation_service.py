"""Atomic orchestration for document generation, ledger writes, and linking."""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from core.domain_errors import (
    DocumentGenerationError,
    ConflictError,
    ProcurementLinkError,
    ValidationError,
)
from services.office_parse_service import generate_docx_isolated
from utils.generation_utils import create_ledger_record
from utils.logger import get_logger


@dataclass(frozen=True)
class ProcurementLink:
    data_sheet_id: int | None = None
    project_id: int | None = None
    source_type: str = 'direct_contract'
    source_id: int | None = None


@dataclass(frozen=True)
class ContractGenerationRequest:
    template: Any
    fields: list[dict[str, Any]]
    field_values: dict[str, Any]
    source_docx: str
    output_path: str
    classification: dict[str, Any] | None = None
    link: ProcurementLink | None = None


@dataclass(frozen=True)
class ContractGenerationResult:
    contract_id: int
    output_path: str
    previous_project_status: str | None = None


class ContractGenerationService:
    def __init__(
        self,
        *,
        ledger_store,
        procurement_store,
        replace_file=os.replace,
        staging_dir=None,
        after_commit=None,
    ):
        self.ledger_store = ledger_store
        self.procurement_store = procurement_store
        self.replace_file = replace_file
        self.staging_dir = os.fspath(staging_dir) if staging_dir else None
        self.after_commit = after_commit or (lambda _result: None)

    @staticmethod
    def _remove(path):
        try:
            if path and os.path.isfile(path):
                os.remove(path)
        except OSError:
            get_logger().warning('Failed to remove generated file: %s', path, exc_info=True)

    def generate(self, request: ContractGenerationRequest) -> ContractGenerationResult:
        """Generate and finalize one contract as a single application operation."""
        output_path = os.path.abspath(request.output_path)
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        # The final rename must stay on one filesystem on Windows. Runtime
        # reconfiguration and tests can replace output_path after this service
        # was constructed, so a cached staging directory is not authoritative.
        staging_dir = os.path.join(output_dir, '.staging')
        os.makedirs(staging_dir, exist_ok=True)
        job_id = uuid.uuid4().hex
        staged_path = os.path.join(
            staging_dir,
            f'{job_id}-{os.path.basename(output_path)}',
        )
        final_created = False
        committed = False

        try:
            self.ledger_store.create_generation_job(job_id, output_path, staged_path)
        except sqlite3.IntegrityError as exc:
            raise ConflictError('同名合同正在生成，请稍后重试', detail=str(exc)) from exc

        try:
            try:
                errors, staged_path = generate_docx_isolated(
                    request.template.data,
                    request.fields,
                    request.field_values,
                    request.source_docx,
                    staged_path,
                )
            except Exception as exc:
                get_logger().error('Document generation failed', exc_info=True)
                raise DocumentGenerationError([str(exc)]) from exc
            if errors:
                raise DocumentGenerationError(errors)
            self.ledger_store.update_generation_job(job_id, 'staged')

            with self.ledger_store.get_conn() as conn:
                try:
                    contract_id = create_ledger_record(
                        request.template,
                        request.fields,
                        request.field_values,
                        output_path,
                        request.classification,
                        conn=conn,
                        document_path=staged_path,
                    )
                except ValueError as exc:
                    raise ValidationError(str(exc), detail=str(exc)) from exc

                previous_status = None
                link = request.link
                if link:
                    try:
                        if link.data_sheet_id is not None:
                            self.procurement_store.complete_contract_link(
                                link.data_sheet_id, contract_id, conn=conn
                            )
                        elif link.project_id is not None:
                            previous_status = self.procurement_store.add_contract_ref(
                                link.project_id,
                                contract_id,
                                source_type=link.source_type,
                                source_id=link.source_id,
                                conn=conn,
                            )
                    except Exception as exc:
                        raise ProcurementLinkError(detail=str(exc)) from exc

                self.replace_file(staged_path, output_path)
                final_created = True
                self.ledger_store.update_generation_job(
                    job_id,
                    'file_moved',
                    contract_id=contract_id,
                    conn=conn,
                )

            committed = True
            result = ContractGenerationResult(
                contract_id=contract_id,
                output_path=output_path,
                previous_project_status=previous_status,
            )
        except Exception as exc:
            if not committed:
                self._remove(staged_path)
                if final_created:
                    self._remove(output_path)
                try:
                    self.ledger_store.update_generation_job(
                        job_id,
                        'failed',
                        error=str(exc),
                    )
                except Exception:
                    get_logger().error(
                        'Failed to record generation failure for job %s',
                        job_id,
                        exc_info=True,
                    )
            raise

        # The contract and final file are now committed. A failure while
        # recording the terminal marker must never delete either one; startup
        # recovery will finalize the durable file_moved state.
        try:
            self.after_commit(result)
            self.ledger_store.update_generation_job(job_id, 'completed')
        except Exception:
            get_logger().error(
                'Generation committed but job finalization failed: %s',
                job_id,
                exc_info=True,
            )
        return result
