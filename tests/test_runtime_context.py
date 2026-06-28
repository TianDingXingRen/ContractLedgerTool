from pathlib import Path


def _assert_context_applied(app_module, base_dir, resource_dir):
    import excel_bill_service
    import ledger_store
    import template_def
    import utils.autostart as autostart
    from services import procurement_file_service
    from utils import helpers

    base = Path(base_dir).resolve()
    resource = Path(resource_dir).resolve()

    assert app_module.RUNTIME_PATHS.base_dir == base
    assert app_module.RUNTIME_PATHS.resource_dir == resource
    assert Path(app_module.BASE_DIR) == base
    assert Path(app_module.RESOURCE_DIR) == resource
    assert Path(app_module.UPLOAD_FOLDER) == base / 'uploads'
    assert Path(app_module.OUTPUT_FOLDER) == base / 'output'
    assert Path(app_module.SESSION_FOLDER) == base / 'sessions'

    assert Path(template_def.TEMPLATES_DIR) == base / 'templates'
    assert Path(ledger_store.DATA_DIR) == base / 'data'
    assert Path(ledger_store.DB_PATH) == base / 'data' / 'contracts.db'
    assert Path(ledger_store.BACKUP_DIR) == base / 'data' / 'backups'
    assert Path(helpers.UPLOAD_FOLDER) == base / 'uploads'
    assert Path(helpers.OUTPUT_FOLDER) == base / 'output'
    assert Path(helpers.SESSION_FOLDER) == base / 'sessions'
    assert Path(helpers.BASE_DIR) == base
    assert Path(autostart.BASE_DIR) == base
    assert Path(excel_bill_service._get_defaults_dir()) == base / 'data' / 'excel_bill_defaults'
    assert procurement_file_service.BASE_DIR == base / 'output' / 'procurement'


def _restore_runtime(app_module, base_dir, resource_dir):
    app_module.reset_runtime()
    app_module.configure_runtime_paths(base_dir, resource_dir)
    app_module.init_runtime(run_maintenance=False)


def test_create_app_applies_runtime_context_to_dependencies(tmp_path):
    import app as app_module

    original_base_dir = app_module.BASE_DIR
    original_resource_dir = app_module.RESOURCE_DIR

    try:
        test_app = app_module.create_app(
            runtime_base_dir=tmp_path,
            resource_dir=original_resource_dir,
            run_maintenance=False,
            testing=True,
        )
        assert test_app.extensions['runtime_paths'].base_dir == tmp_path.resolve()
        _assert_context_applied(app_module, tmp_path, original_resource_dir)
    finally:
        _restore_runtime(app_module, original_base_dir, original_resource_dir)


def test_configure_runtime_paths_keeps_globals_and_modules_in_sync(tmp_path):
    import app as app_module

    original_base_dir = app_module.BASE_DIR
    original_resource_dir = app_module.RESOURCE_DIR

    try:
        paths = app_module.configure_runtime_paths(tmp_path, original_resource_dir)
        assert paths is app_module.RUNTIME_PATHS
        _assert_context_applied(app_module, tmp_path, original_resource_dir)
    finally:
        _restore_runtime(app_module, original_base_dir, original_resource_dir)
