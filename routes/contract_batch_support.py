"""Small reliability helpers shared by contract batch and ledger routes."""

from __future__ import annotations

import os
from contextlib import contextmanager

from utils import helpers
from utils.security import MAX_COUNTERPARTY_LENGTH, limit_text


def remove_generated_file(path, logger):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        logger.warning('Failed to remove generated file: %s', path, exc_info=True)


def discard_generated_contract(
    contract_id, output_path, *, ledger_store, remove_file, logger
):
    discarded = not contract_id
    if contract_id:
        try:
            discarded = bool(ledger_store.discard_unlinked_contract(contract_id))
        except Exception:
            logger.error(
                'Failed to discard unlinked generated contract %s',
                contract_id,
                exc_info=True,
            )
    if discarded:
        remove_file(output_path)
    else:
        logger.error(
            'Preserved generated file because ledger rollback was incomplete: %s',
            output_path,
        )


@contextmanager
def batch_archive(path, failures, archive_factory, compression):
    """Capture ZIP open/write/close failures for compensating rollback."""
    try:
        archive = archive_factory(path, 'w', compression)
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


def rollback_batch_contract(item, *, discard_generated, logger):
    project_id = item.get('project_id')
    contract_id = item['contract_id']
    if project_id is not None:
        try:
            import procurement_store

            procurement_store.remove_contract_ref(
                project_id,
                contract_id,
                restore_status=item.get('previous_status'),
            )
        except Exception:
            logger.error(
                'Batch rollback failed to remove procurement ref for contract %s',
                contract_id,
                exc_info=True,
            )
    discard_generated(contract_id, item['output_path'])


def batch_failure_response(
    failures, archived_contracts, zip_path, *, rollback, remove_file, logger
):
    failure = failures[0]
    logger.error(
        'Batch ZIP finalization failed; rolling back %d contract(s): %s',
        len(archived_contracts),
        failure,
        exc_info=(type(failure), failure, failure.__traceback__),
    )
    for item in reversed(archived_contracts):
        rollback(item)
    remove_file(zip_path)
    return '批量合同归档失败，已回滚本次生成结果', 500


def empty_batch_response(zip_path, errors, remove_file):
    remove_file(zip_path)
    return '批量合同生成失败：\n' + '\n'.join(errors[:20]), 500


def parse_contract_update(form, status):
    classification = helpers.parse_contract_classification(form)
    amount_raw = str(form.get('amount', '') or '').strip()
    amount = helpers.float_or_none(amount_raw)
    if amount_raw and amount is None:
        raise ValueError('合同金额必须是有效数字')
    sign_date_raw = str(form.get('sign_date', '') or '').strip()
    expiry_date_raw = str(form.get('expiry_date', '') or '').strip()
    sign_date = helpers.normalize_date(sign_date_raw) if sign_date_raw else ''
    expiry_date = helpers.normalize_date(expiry_date_raw) if expiry_date_raw else ''
    if sign_date_raw and not sign_date:
        raise ValueError('签订日期格式无效，请使用 YYYY-MM-DD')
    if expiry_date_raw and not expiry_date:
        raise ValueError('到期日期格式无效，请使用 YYYY-MM-DD')
    return {
        'contract_no': limit_text(form.get('contract_no', '').strip(), 80),
        'title': limit_text(form.get('title', '').strip(), 200) or '未命名合同',
        'counterparty': limit_text(
            form.get('counterparty', '').strip(), MAX_COUNTERPARTY_LENGTH
        ),
        'amount': amount,
        'sign_date': sign_date,
        'expiry_date': expiry_date,
        'owner': limit_text(form.get('owner', '').strip(), 60),
        'status': status,
        **classification,
    }
