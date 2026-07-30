from pathlib import Path
from dataclasses import FrozenInstanceError
import importlib

import pytest


def _assert_context_applied(app_module, base_dir, resource_dir):
    import excel_bill_service
    import ledger_store
    import template_def
    import utils.autostart as autostart
    from services import procurement_file_service
    from runtime.app_state import app_state
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
    assert app_state.paths is app_module.RUNTIME_PATHS
    for name in ('UPLOAD_FOLDER', 'OUTPUT_FOLDER', 'SESSION_FOLDER', 'BASE_DIR'):
        assert name not in vars(helpers)
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


def test_importing_app_module_does_not_initialize_runtime():
    import app as app_module

    original_base_dir = app_module.BASE_DIR
    original_resource_dir = app_module.RESOURCE_DIR

    try:
        app_module.reset_runtime()
        reloaded = importlib.reload(app_module)
        assert reloaded._runtime_initialized is False
        assert reloaded._default_app is None
    finally:
        _restore_runtime(app_module, original_base_dir, original_resource_dir)


def test_runtime_base_dir_redirects_frozen_desktop_executable(
    tmp_path, monkeypatch
):
    import app as app_module

    desktop = tmp_path / 'Desktop'
    executable = desktop / 'ContractLedgerTool.exe'
    local_app_data = tmp_path / 'LocalAppData'
    monkeypatch.delenv('CONTRACT_TOOL_RUNTIME_DIR', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(local_app_data))
    monkeypatch.setattr(app_module, '_desktop_dir', lambda: str(desktop))
    monkeypatch.setattr(app_module.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(app_module.sys, 'executable', str(executable))

    assert Path(app_module._runtime_base_dir()) == (
        local_app_data / 'Programs' / 'ContractLedgerTool'
    ).resolve()


def test_runtime_base_dir_keeps_dedicated_install_directory(
    tmp_path, monkeypatch
):
    import app as app_module

    desktop = tmp_path / 'Desktop'
    install_dir = tmp_path / 'NCCAssist' / 'ContractLedgerTool'
    executable = install_dir / 'ContractLedgerTool.exe'
    monkeypatch.delenv('CONTRACT_TOOL_RUNTIME_DIR', raising=False)
    monkeypatch.setattr(app_module, '_desktop_dir', lambda: str(desktop))
    monkeypatch.setattr(app_module.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(app_module.sys, 'executable', str(executable))

    assert Path(app_module._runtime_base_dir()) == install_dir.resolve()


def test_runtime_paths_are_frozen_and_session_stores_are_isolated(tmp_path):
    from runtime.paths import RuntimePaths
    from utils.session_store import load_session_data, save_session_data

    first = RuntimePaths.create(tmp_path / 'first')
    second = RuntimePaths.create(tmp_path / 'second')
    first.ensure_writable_dirs()
    second.ensure_writable_dirs()

    save_session_data('same-id', {'runtime': 'first'}, first)
    save_session_data('same-id', {'runtime': 'second'}, second)

    assert load_session_data('same-id', first) == {'runtime': 'first'}
    assert load_session_data('same-id', second) == {'runtime': 'second'}
    with pytest.raises(FrozenInstanceError):
        first.base_dir = second.base_dir
