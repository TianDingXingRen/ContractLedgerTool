"""Runtime context wiring for writable paths and dependent modules."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.paths import RuntimePaths


@dataclass(frozen=True)
class RuntimeContext:
    """Resolved runtime/resource paths used by the application."""

    paths: RuntimePaths

    @property
    def base_dir(self):
        return self.paths.base_dir

    @property
    def resource_dir(self):
        return self.paths.resource_dir


def create_runtime_context(base_dir, resource_dir=None):
    """Create a runtime context from the writable and bundled resource roots."""
    return RuntimeContext(paths=RuntimePaths.create(base_dir, resource_dir))


def apply_runtime_context(context: RuntimeContext) -> RuntimeContext:
    """Apply runtime paths to modules that keep path globals for compatibility."""
    paths = context.paths

    import template_def
    import ledger_store
    import excel_bill_service
    import utils.autostart as autostart
    from utils import helpers
    from services import procurement_file_service

    template_def.TEMPLATES_DIR = str(paths.templates_dir)

    ledger_store.DATA_DIR = str(paths.data_dir)
    ledger_store.DB_PATH = str(paths.database_file)
    ledger_store.BACKUP_DIR = str(paths.backups_dir)

    helpers.UPLOAD_FOLDER = str(paths.uploads_dir)
    helpers.OUTPUT_FOLDER = str(paths.output_dir)
    helpers.SESSION_FOLDER = str(paths.sessions_dir)
    helpers.BASE_DIR = str(paths.base_dir)

    autostart.BASE_DIR = str(paths.base_dir)
    excel_bill_service.configure_defaults_dir(paths.excel_bill_defaults_dir)
    procurement_file_service.configure_base_dir(paths.procurement_dir)

    return context
