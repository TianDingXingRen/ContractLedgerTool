"""Startup reconciliation and diagnostics for interrupted generations."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from utils.logger import get_logger


class GenerationRecoveryService:
    def __init__(
        self,
        *,
        ledger_store,
        output_dir,
        staging_dir=None,
        recovery_dir=None,
        additional_staging_dirs=None,
    ):
        self.ledger_store = ledger_store
        self.output_dir = Path(output_dir).resolve()
        self.staging_dir = Path(staging_dir or self.output_dir / '.staging').resolve()
        additional_staging_dirs = (
            additional_staging_dirs
            if additional_staging_dirs is not None
            else (self.output_dir.parent / 'uploads',)
        )
        self.staging_dirs = (
            self.staging_dir,
            *(Path(path).resolve() for path in additional_staging_dirs),
        )
        self.recovery_dir = Path(recovery_dir or self.output_dir / '.recovery').resolve()
        if not self._within(self.output_dir, self.recovery_dir):
            raise ValueError('恢复隔离目录必须位于合同输出目录内')

    @staticmethod
    def _within(root: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve(self, stored_path, *, roots, label):
        raw = str(stored_path or '').strip()
        if not raw:
            raise ValueError(f'{label}为空')
        # Recovery journal paths need their original identity even when the
        # source no longer exists.  The general document resolver intentionally
        # rebases missing legacy absolute paths, which would turn a boundary
        # check into a check of a different path.
        candidate = Path(raw) if os.path.isabs(raw) else Path(
            self.ledger_store.resolve_docx_path(raw)
        )
        resolved = candidate.resolve()
        if not any(self._within(root, resolved) for root in roots):
            raise ValueError(f'{label}超出允许运行目录')
        return resolved

    def _resolve_job_paths(self, job):
        return (
            self._resolve(
                job.get('output_path'), roots=(self.output_dir,), label='合同输出路径'
            ),
            self._resolve(
                job.get('staging_path'), roots=self.staging_dirs, label='合同暂存路径'
            ),
        )

    def _isolate(self, source: Path, job_id: str, label: str, *, roots):
        resolved_source = source.resolve()
        if not any(self._within(root, resolved_source) for root in roots):
            raise ValueError('待隔离文件超出允许运行目录')
        if not resolved_source.is_file():
            return ''
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        safe_job_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(job_id))[:80]
        safe_job_id = safe_job_id.replace('..', '_').strip('._') or 'unknown'
        safe_label = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(label))[:24] or 'file'
        target = self.recovery_dir / (
            f'{safe_job_id}-{safe_label}-{resolved_source.name}'
        )
        if target.exists():
            target = self.recovery_dir / (
                f'{safe_job_id}-{safe_label}-{uuid.uuid4().hex[:8]}-'
                f'{resolved_source.name}'
            )
        target = target.resolve()
        if not self._within(self.recovery_dir, target):
            raise ValueError('恢复隔离目标超出允许运行目录')
        os.replace(resolved_source, target)
        return str(target)

    def _recover_job(self, job):
        job_id = job['job_id']
        try:
            output_path, staging_path = self._resolve_job_paths(job)
        except ValueError as exc:
            self.ledger_store.update_generation_job(
                job_id,
                'attention',
                error=str(exc),
                recovery_action='rejected_unsafe_generation_paths',
            )
            return 'attention'
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
        for source, label, roots in (
            (staging_path, 'stage', self.staging_dirs),
            (output_path, 'final', (self.output_dir,)),
        ):
            target = self._isolate(source, job_id, label, roots=roots)
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
            roots = (
                (self.staging_dir,)
                if self._within(self.staging_dir, source.resolve())
                else (self.output_dir,)
            )
            target = self._isolate(
                source, 'untracked', 'stage', roots=roots
            )
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
        additional_staging_dirs=(paths.uploads_dir,),
    ).reconcile()
