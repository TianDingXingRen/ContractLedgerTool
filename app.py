"""合同模板制作与生成工具 - Flask Web 应用"""

import argparse
import json
import os
import signal
import sys
import tempfile
import threading

from flask import Flask
from werkzeug.local import LocalProxy

import ledger_store
import procurement_store
from runtime.maintenance import cleanup_old_files, seed_packaged_assets
from services.generation_recovery_service import reconcile_generation_jobs
from core.app_errors import register_error_handlers
from core.app_hooks import register_security_hooks
from core.app_secrets import load_or_create_secret_key
from core.app_startup import open_browser_later, should_open_browser, validate_bind_host
from core.app_template_context import csrf_token, register_template_context
from utils.logger import setup_logging, get_logger, close_logging
from config import config as app_config
from runtime.context import apply_runtime_context, create_runtime_context
from runtime.services import create_runtime_services

# ── Path resolution ──


def _runtime_base_dir():
    override = os.environ.get('CONTRACT_TOOL_RUNTIME_DIR')
    if override:
        return os.path.abspath(override)
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource_base_dir():
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _runtime_base_dir()
RESOURCE_DIR = _resource_base_dir()

# ── Directory setup ──

_runtime_initialized = False
_last_generation_recovery_report = None
_RUNTIME_CONTEXT = create_runtime_context(BASE_DIR, RESOURCE_DIR)
RUNTIME_PATHS = _RUNTIME_CONTEXT.paths
UPLOAD_FOLDER = str(RUNTIME_PATHS.uploads_dir)
OUTPUT_FOLDER = str(RUNTIME_PATHS.output_dir)
SESSION_FOLDER = str(RUNTIME_PATHS.sessions_dir)


def _sync_runtime_globals(context):
    """Keep app.py compatibility globals aligned with the active context."""
    global BASE_DIR, RESOURCE_DIR, RUNTIME_PATHS
    global UPLOAD_FOLDER, OUTPUT_FOLDER, SESSION_FOLDER

    paths = context.paths
    RUNTIME_PATHS = paths
    BASE_DIR = str(paths.base_dir)
    RESOURCE_DIR = str(paths.resource_dir)
    UPLOAD_FOLDER = str(paths.uploads_dir)
    OUTPUT_FOLDER = str(paths.output_dir)
    SESSION_FOLDER = str(paths.sessions_dir)


def configure_runtime_paths(base_dir=None, resource_dir=None):
    """统一配置所有模块的可写目录，并允许测试创建隔离应用。"""
    global _RUNTIME_CONTEXT, _runtime_initialized

    old_signature = (
        os.path.abspath(BASE_DIR), os.path.abspath(RESOURCE_DIR)
    )
    context = create_runtime_context(base_dir or BASE_DIR, resource_dir or RESOURCE_DIR)
    paths = context.paths
    new_signature = (str(paths.base_dir), str(paths.resource_dir))
    if old_signature != new_signature and _runtime_initialized:
        close_logging()

    _RUNTIME_CONTEXT = apply_runtime_context(context)
    _sync_runtime_globals(_RUNTIME_CONTEXT)
    app_config.reload(BASE_DIR)
    _runtime_initialized = False
    return paths


configure_runtime_paths(BASE_DIR, RESOURCE_DIR)

# ── Secret key persistence ──


def _load_or_create_secret_key():
    """Compatibility wrapper for Flask secret key persistence."""
    return load_or_create_secret_key(BASE_DIR)


def _cleanup_old_files(max_age_days=None):
    """Compatibility wrapper for runtime file cleanup."""
    return cleanup_old_files(
        RUNTIME_PATHS, app_config, max_age_days=max_age_days
    )

_runtime_lock = threading.Lock()

def init_runtime(run_maintenance=True):
    """Initialize writable paths, logging, database, and packaged assets once.
    线程安全：通过 _runtime_lock 确保只初始化一次。"""
    global _runtime_initialized, _last_generation_recovery_report
    with _runtime_lock:
        if _runtime_initialized:
            return

        RUNTIME_PATHS.ensure_writable_dirs()

        # 首次运行时自动生成 config.json（如果不存在）
        from config import ensure_config_file
        ensure_config_file(BASE_DIR)
        app_config.reload(BASE_DIR)

        level = getattr(__import__('logging'), app_config.LOG_LEVEL.upper(), 20)
        setup_logging(os.path.join(BASE_DIR, 'logs'), level=level)

        # Capture the last pre-upgrade state before any schema initialization
        # or migration. A failed migration must not be the only recoverable copy.
        if os.path.isfile(ledger_store.DB_PATH) and (
            ledger_store.needs_migration() or procurement_store.needs_migration()
        ):
            backup = ledger_store.create_backup(label='before_upgrade')
            get_logger().info('Created pre-upgrade database backup: %s', backup['path'])

        ledger_store.init_db()
        procurement_store.init_db()
        _last_generation_recovery_report = reconcile_generation_jobs(
            RUNTIME_PATHS,
            ledger_store,
        )
        if _last_generation_recovery_report['errors']:
            get_logger().warning(
                'Generation recovery completed with errors: %s',
                _last_generation_recovery_report['errors'],
            )
        elif _last_generation_recovery_report['inspected']:
            get_logger().info(
                'Generation recovery reconciled %d interrupted job(s)',
                _last_generation_recovery_report['inspected'],
            )
        if run_maintenance:
            ledger_store.backup_database()
            _cleanup_old_files(max_age_days=app_config.CLEANUP_DAYS)
        _seed_packaged_assets()
        _runtime_initialized = True

# ── App factory ──


def create_app(runtime_base_dir=None, resource_dir=None, run_maintenance=True, testing=False):
    if runtime_base_dir is not None or resource_dir is not None:
        configure_runtime_paths(
            runtime_base_dir or BASE_DIR,
            resource_dir or RESOURCE_DIR,
        )
    init_runtime(run_maintenance=run_maintenance)
    app = Flask(
        __name__,
        template_folder=os.path.join(RESOURCE_DIR, 'templates'),
        static_folder=os.path.join(RESOURCE_DIR, 'static'),
    )
    app.secret_key = _load_or_create_secret_key()
    app.config['TESTING'] = bool(testing)
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['MAX_CONTENT_LENGTH'] = app_config.MAX_CONTENT_LENGTH_MB * 1024 * 1024
    app.extensions['runtime_paths'] = RUNTIME_PATHS
    app.extensions['contract_tool'] = create_runtime_services(RUNTIME_PATHS)

    register_security_hooks(app, app_config)
    register_template_context(app, _csrf_token)

    # ── Register routes ──
    from routes import register_all
    register_all(app)

    register_error_handlers(app)

    return app


def _csrf_token():
    """Compatibility wrapper for template CSRF token generation."""
    return csrf_token()


def _seed_packaged_assets():
    """Compatibility wrapper for packaged runtime asset seeding."""
    return seed_packaged_assets(RUNTIME_PATHS)

# ── Lazy compatibility app instance ──

_default_app = None
_default_app_lock = threading.Lock()


def get_default_app():
    """Create the compatibility Flask app only when it is first used."""
    global _default_app
    if _default_app is not None:
        return _default_app
    with _default_app_lock:
        if _default_app is None:
            _default_app = create_app()
    return _default_app


app = LocalProxy(get_default_app)


def _shutdown():
    get_logger().info('Shutting down...')
    try:
        ledger_store.close_connections()
    except Exception:
        get_logger().warning('关闭数据库连接时出错', exc_info=True)
    close_logging()


def reset_runtime():
    """释放运行时资源，主要供测试 teardown 使用。"""
    global _runtime_initialized, _default_app, _last_generation_recovery_report
    try:
        ledger_store.close_connections()
    except Exception:
        get_logger().debug('reset_runtime failed to close database connections', exc_info=True)
    close_logging()
    _runtime_initialized = False
    _last_generation_recovery_report = None
    _default_app = None


def _signal_handler(signum, frame):
    _shutdown()
    sys.exit(0)


def _register_signal_handlers():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def _open_browser_later(url):
    """Compatibility wrapper for delayed browser startup."""
    open_browser_later(url)


def run_self_check(runtime_base_dir=None):
    """Initialize an isolated runtime and verify HTTP plus SQLite health."""
    original_base_dir = BASE_DIR
    original_resource_dir = RESOURCE_DIR

    def _check(directory):
        try:
            flask_app = create_app(
                runtime_base_dir=directory,
                resource_dir=original_resource_dir,
                run_maintenance=False,
                testing=True,
            )
            with flask_app.test_client() as client:
                response = client.get('/')
                http_ok = response.status_code == 200
                response.close()
            with ledger_store.get_conn() as conn:
                integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            result = {
                'ok': http_ok and integrity == 'ok',
                'http_status': 200 if http_ok else 500,
                'integrity_check': integrity,
                'ledger_schema': ledger_store.get_schema_version(),
                'procurement_schema': procurement_store.get_schema_version(),
                'generation_integrity': flask_app.extensions[
                    'contract_tool'
                ].generation_recovery.diagnostics(),
            }
            result['ok'] = result['ok'] and result['generation_integrity']['ok']
            print(json.dumps(result, ensure_ascii=False))
            return result['ok']
        finally:
            reset_runtime()
            configure_runtime_paths(original_base_dir, original_resource_dir)

    if runtime_base_dir:
        os.makedirs(runtime_base_dir, exist_ok=True)
        return _check(os.path.abspath(runtime_base_dir))
    with tempfile.TemporaryDirectory(prefix='contract-tool-self-check-') as directory:
        return _check(directory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=app_config.HOST)
    parser.add_argument('--port', default=app_config.PORT, type=int)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--runtime-dir')
    args = parser.parse_args()
    if args.self_check:
        sys.exit(0 if run_self_check(args.runtime_dir) else 1)
    try:
        validate_bind_host(args.host, app_config.ALLOW_REMOTE)
    except ValueError as exc:
        parser.error(str(exc))
    flask_app = get_default_app()
    _register_signal_handlers()
    if should_open_browser(args.no_browser, app_config.DEBUG):
        _open_browser_later(f'http://{args.host}:{args.port}/')
    try:
        flask_app.run(debug=app_config.DEBUG, host=args.host, port=args.port)
    finally:
        _shutdown()
