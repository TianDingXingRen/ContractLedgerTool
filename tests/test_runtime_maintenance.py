import json
import os
import time
from types import SimpleNamespace

from runtime.paths import RuntimePaths
from runtime import maintenance as runtime_maintenance


def _touch_old(path, days=10):
    path.write_text('old', encoding='utf-8')
    old_time = time.time() - days * 86400
    os.utime(path, (old_time, old_time))


def test_cleanup_old_files_preserves_referenced_outputs_and_template_uploads(tmp_path, monkeypatch):
    import ledger_store
    import template_def

    paths = RuntimePaths.create(tmp_path)
    paths.ensure_writable_dirs()

    old_output = paths.output_dir / 'old-output.docx'
    preserved_output = paths.output_dir / 'preserved-output.docx'
    old_upload = paths.uploads_dir / 'old-upload.docx'
    preserved_upload = paths.uploads_dir / 'preserved-upload.docx'
    old_session = paths.sessions_dir / 'old-session.json'
    fresh_session = paths.sessions_dir / 'fresh-session.json'

    for path in (old_output, preserved_output, old_upload, preserved_upload, old_session):
        _touch_old(path)
    fresh_session.write_text('{}', encoding='utf-8')

    template_path = paths.templates_dir / 'sample.contract-template'
    template_path.write_text(
        json.dumps({
            'format_version': '1.0',
            'template_name': 'sample',
            'source_docx': preserved_upload.name,
            'fields': [],
        }, ensure_ascii=False),
        encoding='utf-8',
    )

    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(paths.templates_dir))
    monkeypatch.setattr(ledger_store, 'get_all_docx_paths', lambda: [str(preserved_output)])

    config = SimpleNamespace(OUTPUT_CLEANUP_DAYS=1, SESSION_TTL_HOURS=1)
    runtime_maintenance.cleanup_old_files(paths, config)

    assert not old_output.exists()
    assert preserved_output.exists()
    assert not old_upload.exists()
    assert preserved_upload.exists()
    assert not old_session.exists()
    assert fresh_session.exists()


def test_seed_packaged_assets_copies_once_and_skips_same_version_overwrite(
    tmp_path,
    monkeypatch,
):
    resource_dir = tmp_path / 'resource'
    runtime_dir = tmp_path / 'runtime'
    paths = RuntimePaths.create(runtime_dir, resource_dir)
    paths.ensure_writable_dirs()

    (resource_dir / 'templates').mkdir(parents=True)
    (resource_dir / 'uploads').mkdir(parents=True)
    (resource_dir / 'installer_assets').mkdir(parents=True)
    (resource_dir / 'version.txt').write_text('20260628.1', encoding='utf-8')
    (resource_dir / 'templates' / 'sample.contract-template').write_text('template-v1', encoding='utf-8')
    (resource_dir / 'uploads' / 'sample.docx').write_text('upload-v1', encoding='utf-8')
    (resource_dir / 'installer_assets' / 'start.ps1').write_text('start-v1', encoding='utf-8')
    (resource_dir / 'installer_assets' / 'stop.ps1').write_text('stop-v1', encoding='utf-8')

    chmod_calls = []
    monkeypatch.setattr(
        runtime_maintenance.os,
        'chmod',
        lambda path, mode: chmod_calls.append((path, mode)),
    )

    runtime_maintenance.seed_packaged_assets(paths)

    target_template = paths.templates_dir / 'sample.contract-template'
    assert target_template.read_text(encoding='utf-8') == 'template-v1'
    assert (paths.uploads_dir / 'sample.docx').read_text(encoding='utf-8') == 'upload-v1'
    assert (paths.base_dir / 'start.ps1').read_text(encoding='utf-8') == 'start-v1'
    assert (paths.base_dir / 'stop.ps1').read_text(encoding='utf-8') == 'stop-v1'
    assert (paths.base_dir / '.installed_version').read_text(encoding='utf-8') == '20260628.1'
    assert [mode for _path, mode in chmod_calls] == [0o400, 0o400]

    target_template.write_text('user-edit', encoding='utf-8')
    runtime_maintenance.seed_packaged_assets(paths)

    assert target_template.read_text(encoding='utf-8') == 'user-edit'


def test_cleanup_skips_uploads_when_a_template_is_malformed(tmp_path, monkeypatch):
    import ledger_store
    import template_def

    paths = RuntimePaths.create(tmp_path)
    paths.ensure_writable_dirs()
    old_upload = paths.uploads_dir / 'must-not-be-deleted.docx'
    _touch_old(old_upload)
    malformed = paths.templates_dir / 'malformed.contract-template'
    malformed.write_text('1.25', encoding='utf-8')

    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(paths.templates_dir))
    monkeypatch.setattr(ledger_store, 'get_all_docx_paths', lambda: [])
    config = SimpleNamespace(OUTPUT_CLEANUP_DAYS=1, SESSION_TTL_HOURS=1)

    runtime_maintenance.cleanup_old_files(paths, config)

    assert old_upload.exists()


def test_cleanup_skips_all_file_deletion_when_ledger_paths_are_unavailable(
    tmp_path,
    monkeypatch,
):
    import sqlite3

    import ledger_store

    paths = RuntimePaths.create(tmp_path)
    paths.ensure_writable_dirs()
    referenced_output = paths.output_dir / 'referenced-contract.docx'
    _touch_old(referenced_output)

    def _query_failed():
        raise sqlite3.OperationalError('database is unavailable')

    monkeypatch.setattr(ledger_store, 'get_all_docx_paths', _query_failed)
    config = SimpleNamespace(OUTPUT_CLEANUP_DAYS=1, SESSION_TTL_HOURS=1)

    runtime_maintenance.cleanup_old_files(paths, config)

    assert referenced_output.exists()


def test_cleanup_removes_nested_recovery_and_trash_files(tmp_path, monkeypatch):
    import ledger_store
    import template_def

    paths = RuntimePaths.create(tmp_path)
    paths.ensure_writable_dirs()
    old_staging = paths.generation_staging_dir / 'job' / 'partial.docx'
    old_recovery = paths.generation_recovery_dir / 'job' / 'recovered.docx'
    old_trash = paths.data_dir / 'invoice_files' / '.trash' / 'job' / 'invoice.pdf'
    for path in (old_staging, old_recovery, old_trash):
        path.parent.mkdir(parents=True, exist_ok=True)
        _touch_old(path)

    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(paths.templates_dir))
    monkeypatch.setattr(ledger_store, 'get_all_docx_paths', lambda: [])
    monkeypatch.setattr(ledger_store, 'list_unfinished_generation_jobs', lambda: [])
    monkeypatch.setattr(ledger_store, 'prune_generation_job_history', lambda _cutoff: 0)
    config = SimpleNamespace(
        OUTPUT_CLEANUP_DAYS=1,
        CLEANUP_DAYS=1,
        SESSION_TTL_HOURS=1,
        GENERATION_HISTORY_DAYS=30,
    )

    runtime_maintenance.cleanup_old_files(paths, config)

    assert not old_staging.exists()
    assert not old_recovery.exists()
    assert not old_trash.exists()


def test_generation_history_pruning_retains_attention_rows(tmp_db):
    import ledger_store

    old = '2020-01-01 00:00:00'
    with ledger_store.get_conn() as connection:
        for state in ('completed', 'failed', 'recovered', 'attention'):
            connection.execute(
                """INSERT INTO contract_generation_jobs (
                       job_id, state, output_path, staging_path,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    f'old-{state}',
                    state,
                    f'output/{state}.docx',
                    f'output/.staging/{state}.docx',
                    old,
                    old,
                ),
            )

    assert ledger_store.prune_generation_job_history(
        '2021-01-01 00:00:00'
    ) == 3
    with ledger_store.get_conn() as connection:
        remaining = {
            row['state']
            for row in connection.execute(
                'SELECT state FROM contract_generation_jobs'
            ).fetchall()
        }
    assert remaining == {'attention'}
