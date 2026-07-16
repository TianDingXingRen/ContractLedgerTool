"""Startup reconciliation and diagnostics for interrupted generations."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from utils.logger import get_logger


class GenerationRecoveryService:
    def __init__(self, *, ledger_store, output_dir, staging_dir=None, recovery_dir=None):
        self.ledger_store = ledger_store
        self.output_dir = Path(output_dir)
        self.staging_dir = Path(staging_dir or self.output_dir / '.staging')
        self.recovery_dir = Path(recovery_dir or self.output_dir / '.recovery')

    def _resolve(self, stored_path):
        return Path(self.ledger_store.resolve_docx_path(stored_path))

    def _isolate(self, source: Path, job_id: str, label: str):
        if not source.is_file():
            return ''
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        target = self.recovery_dir / f'{job_id}-{label}-{source.name}'
        if target.exists():
            target = self.recovery_dir / (
                f'{job_id}-{label}-{uuid.uuid4().hex[:8]}-{source.name}'
            )
        os.replace(source, target)
        return str(target)

    def _recover_job(self, job):
        job_id = job['job_id']
        output_path = self._resolve(job['output_path'])
        staging_path = self._resolve(job['staging_path'])
        contract = (
            self.ledger_store.get_contract(job['contract_id'])
            if job.get('contract_id')
            else None
        )

        if contract:
            if output_path.is_file():
                self.ledger_store.update_generation_job(
                    job_id,
                    'completed',
                    recovery_action='finalized_committed_job',
                )
                return 'completed'
            if staging_path.is_file():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging_path, output_path)
                self.ledger_store.update_generation_job(
                    job_id,
                    'completed',
                    recovery_action='restored_committed_file',
                )
                return 'completed'
            self.ledger_store.update_generation_job(
                job_id,
                'attention',
                error='Ledger record exists but generated document is missing',
                recovery_action='manual_review_required',
            )
            return 'attention'

        isolated = []
        for source, label in ((staging_path, 'stage'), (output_path, 'final')):
            target = self._isolate(source, job_id, label)
            if target:
                isolated.append(target)
        self.ledger_store.update_generation_job(
            job_id,
            'recovered',
            recovery_action=(
                'isolated_uncommitted_files:' + '|'.join(isolated)
                if isolated
                else 'closed_uncommitted_job_without_files'
            ),
        )
        return 'recovered'

    def _isolate_untracked_staging_files(self):
        isolated = []
        candidates = []
        if self.staging_dir.is_dir():
            candidates.extend(path for path in self.staging_dir.iterdir() if path.is_file())
        if self.output_dir.is_dir():
            candidates.extend(self.output_dir.glob('*.stage-*'))
        for source in candidates:
            target = self._isolate(source, 'untracked', 'stage')
            if target:
                isolated.append(target)
        return isolated

    def reconcile(self):
        report = {
            'inspected': 0,
            'completed': 0,
            'recovered': 0,
            'attention': 0,
            'isolated_files': [],
            'errors': [],
        }
        for job in self.ledger_store.list_unfinished_generation_jobs():
            report['inspected'] += 1
            try:
                outcome = self._recover_job(job)
                report[outcome] += 1
            except Exception as exc:
                report['errors'].append({'job_id': job['job_id'], 'error': str(exc)})
                get_logger().error(
                    'Failed to recover generation job %s',
                    job['job_id'],
                    exc_info=True,
                )
        try:
            report['isolated_files'] = self._isolate_untracked_staging_files()
        except Exception as exc:
            report['errors'].append({'job_id': 'untracked', 'error': str(exc)})
            get_logger().error('Failed to isolate untracked staging files', exc_info=True)
        return report

    def diagnostics(self):
        counts = self.ledger_store.get_generation_job_state_counts()
        missing = []
        for path in self.ledger_store.get_all_docx_paths():
            if path and not os.path.isfile(path):
                missing.append(path)
        staging_files = []
        if self.staging_dir.is_dir():
            staging_files.extend(str(path) for path in self.staging_dir.iterdir() if path.is_file())
        if self.output_dir.is_dir():
            staging_files.extend(str(path) for path in self.output_dir.glob('*.stage-*'))
        unfinished = sum(counts.get(state, 0) for state in ('prepared', 'staged', 'file_moved'))
        return {
            'ok': unfinished == 0 and counts.get('attention', 0) == 0 and not missing,
            'unfinished': unfinished,
            'attention': counts.get('attention', 0),
            'completed': counts.get('completed', 0),
            'recovered': counts.get('recovered', 0),
            'failed': counts.get('failed', 0),
            'missing_documents': len(missing),
            'missing_document_samples': missing[:5],
            'staging_files': len(staging_files),
        }


def reconcile_generation_jobs(paths, ledger_store):
    return GenerationRecoveryService(
        ledger_store=ledger_store,
        output_dir=paths.output_dir,
        staging_dir=paths.generation_staging_dir,
        recovery_dir=paths.generation_recovery_dir,
    ).reconcile()
