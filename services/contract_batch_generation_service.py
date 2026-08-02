"""Batch contract generation, ZIP finalization, and compensating rollback."""

from __future__ import annotations

import os
import uuid
import zipfile
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import ledger_store
import procurement_store
from core.domain_errors import (
    DocumentGenerationError,
    ProcurementLinkError,
    ValidationError,
)
from services.contract_generation_service import ContractGenerationRequest, ProcurementLink
from utils.field_utils import safe_filename_part
from utils.generation_utils import contract_number_keys, recalculate_scalar_fields
from utils.logger import get_logger


class BatchGenerationFailure(RuntimeError):
    """A batch failure whose message is safe to return to the user."""

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


@dataclass(frozen=True)
class BatchGenerationCommand:
    sid: str
    template: Any
    fields: list[dict[str, Any]]
    field_values: dict[str, Any]
    classification: dict[str, Any]
    counterparties: list[str]
    batch_field_keys: list[str]
    source_docx: str
    output_dir: str
    generation_service: Any
    template_name: str = ''
    source_project_id: int | None = None
    source_type: str = 'direct_contract'
    source_id: int | None = None


@dataclass(frozen=True)
class BatchGenerationResult:
    zip_path: str
    download_name: str
    success_count: int
    errors: list[str]


def _remove_generated_file(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        get_logger().warning(
            'Failed to remove generated file: %s',
            path,
            exc_info=True,
        )


def _discard_generated_contract(contract_id: int | None, output_path: str) -> None:
    discarded = not contract_id
    if contract_id:
        try:
            discarded = bool(ledger_store.discard_unlinked_contract(contract_id))
        except Exception:
            get_logger().error(
                'Failed to discard unlinked generated contract %s',
                contract_id,
                exc_info=True,
            )
    if discarded:
        _remove_generated_file(output_path)
    else:
        get_logger().error(
            'Preserved generated file because ledger rollback was incomplete: %s',
            output_path,
        )


@contextmanager
def _batch_archive(path: str, failures: list[Exception]):
    """Capture ZIP open/body/close failures for compensating rollback."""
    try:
        archive = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED)
    except Exception as exc:
        failures.append(exc)
        yield None
        return
    try:
        yield archive
    except Exception as exc:
        failures.append(exc)
    finally:
        try:
            archive.close()
        except Exception as exc:
            failures.append(exc)


def _rollback_batch_contract(item: dict[str, Any]) -> None:
    project_id = item.get('project_id')
    contract_id = item['contract_id']
    if project_id is not None:
        try:
            procurement_store.remove_contract_ref(
                project_id,
                contract_id,
                restore_status=item.get('previous_status'),
            )
        except Exception:
            get_logger().error(
                'Batch rollback failed to remove procurement ref for contract %s',
                contract_id,
                exc_info=True,
            )
    _discard_generated_contract(contract_id, item['output_path'])


def _batch_values(
    command: BatchGenerationCommand,
    index: int,
    counterparty: str,
    number_keys: list[str],
) -> tuple[dict[str, Any], list[str]]:
    values = deepcopy(command.field_values)
    for field_key in command.batch_field_keys:
        values[field_key] = counterparty
    for number_key in number_keys:
        base_number = str(command.field_values.get(number_key) or '').strip()
        if base_number:
            values[number_key] = f'{base_number}-{index + 1:03d}'
    return values, recalculate_scalar_fields(command.fields, values)


def _generate_one(
    command: BatchGenerationCommand,
    index: int,
    counterparty: str,
    number_keys: list[str],
    run_id: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    values, calculation_errors = _batch_values(
        command,
        index,
        counterparty,
        number_keys,
    )
    if calculation_errors:
        return None, [f'{counterparty}: {error}' for error in calculation_errors]

    suffix = safe_filename_part(counterparty, f'contract_{index + 1}')[:30]
    output_path = os.path.join(
        command.output_dir,
        f'{command.sid}_{run_id}_batch_{index}_{suffix}.docx',
    )
    link = None
    if command.source_project_id is not None:
        link = ProcurementLink(
            project_id=command.source_project_id,
            source_type=command.source_type,
            source_id=command.source_id,
        )
    try:
        result = command.generation_service.generate(
            ContractGenerationRequest(
                template=command.template,
                fields=command.fields,
                field_values=values,
                source_docx=command.source_docx,
                output_path=output_path,
                classification=command.classification,
                link=link,
            )
        )
    except DocumentGenerationError as exc:
        details = exc.errors or ['合同生成失败']
        return None, [f'{counterparty}: {detail}' for detail in details]
    except ValidationError:
        return None, [f'{counterparty}: 台账入账失败']
    except ProcurementLinkError:
        return None, [f'{counterparty}: 采购项目关联失败']
    except Exception:
        get_logger().error('Batch generation transaction failed', exc_info=True)
        return None, [f'{counterparty}: 合同生成失败']

    return {
        'contract_id': result.contract_id,
        'output_path': result.output_path,
        'project_id': command.source_project_id,
        'previous_status': result.previous_project_status,
    }, []


def _rollback_failed_archive(
    failures: list[Exception],
    archived_contracts: list[dict[str, Any]],
    zip_path: str,
) -> None:
    failure = failures[0]
    get_logger().error(
        'Batch ZIP finalization failed; rolling back %d contract(s): %s',
        len(archived_contracts),
        failure,
        exc_info=(type(failure), failure, failure.__traceback__),
    )
    for item in reversed(archived_contracts):
        _rollback_batch_contract(item)
    _remove_generated_file(zip_path)


def generate_batch_archive(
    command: BatchGenerationCommand,
) -> BatchGenerationResult:
    """Generate a batch and expose it only after the ZIP closes successfully."""
    zip_path = os.path.join(
        command.output_dir,
        f'{command.sid}_{uuid.uuid4().hex[:8]}_batch.zip',
    )
    errors: list[str] = []
    archive_failures: list[Exception] = []
    archived_contracts: list[dict[str, Any]] = []
    success_count = 0
    number_keys = contract_number_keys(command.fields)
    run_id = uuid.uuid4().hex[:12]

    with _batch_archive(zip_path, archive_failures) as archive:
        for index, counterparty in (
            enumerate(command.counterparties) if archive is not None else ()
        ):
            item, item_errors = _generate_one(
                command,
                index,
                counterparty,
                number_keys,
                run_id,
            )
            errors.extend(item_errors)
            if item is None:
                continue
            archived_contracts.append(item)
            archive_name = (
                f'{index + 1:03d}_'
                f'{safe_filename_part(counterparty, f"contract_{index + 1}")}'
                '_合同.docx'
            )
            try:
                archive.write(item['output_path'], archive_name)
                success_count += 1
            except Exception as exc:
                get_logger().error('Batch ZIP write failed', exc_info=True)
                errors.append(f'{counterparty}: ZIP 写入失败')
                _rollback_batch_contract(item)
                archived_contracts.remove(item)
                archive_failures.append(exc)
                break

    if archive_failures:
        _rollback_failed_archive(archive_failures, archived_contracts, zip_path)
        raise BatchGenerationFailure('批量合同归档失败，已回滚本次生成结果')
    if success_count == 0:
        _remove_generated_file(zip_path)
        raise BatchGenerationFailure(
            '批量合同生成失败：\n' + '\n'.join(errors[:20])
        )

    download_name = (
        f'{command.template_name}_批量合同_{success_count}份.zip'
        if command.template_name
        else f'批量合同_{success_count}份.zip'
    )
    return BatchGenerationResult(
        zip_path=zip_path,
        download_name=download_name,
        success_count=success_count,
        errors=errors,
    )
