import json
import os
import time
from types import SimpleNamespace

from runtime_paths import RuntimePaths
import runtime_maintenance


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


def test_seed_packaged_assets_copies_once_and_skips_same_version_overwrite(tmp_path):
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

    runtime_maintenance.seed_packaged_assets(paths)

    target_template = paths.templates_dir / 'sample.contract-template'
    assert target_template.read_text(encoding='utf-8') == 'template-v1'
    assert (paths.uploads_dir / 'sample.docx').read_text(encoding='utf-8') == 'upload-v1'
    assert (paths.base_dir / 'start.ps1').read_text(encoding='utf-8') == 'start-v1'
    assert (paths.base_dir / 'stop.ps1').read_text(encoding='utf-8') == 'stop-v1'
    assert (paths.base_dir / '.installed_version').read_text(encoding='utf-8') == '20260628.1'

    target_template.write_text('user-edit', encoding='utf-8')
    runtime_maintenance.seed_packaged_assets(paths)

    assert target_template.read_text(encoding='utf-8') == 'user-edit'
