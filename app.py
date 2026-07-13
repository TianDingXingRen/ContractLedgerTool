"""合同模板制作与生成工具 - Flask Web 应用"""

import os
import sys
import signal
import argparse
import threading

from flask import Flask

import ledger_store
import procurement_store
from runtime.maintenance import cleanup_old_files, seed_packaged_assets
from core.app_errors import register_error_handlers
from core.app_hooks import register_security_hooks
from core.app_secrets import load_or_create_secret_key
from core.app_startup import open_browser_later, should_open_browser
from core.app_template_context import csrf_token, register_template_context
from utils.logger import setup_logging, get_logger, close_logging
from config import config as app_config
from runtime.context import apply_runtime_context, create_runtime_context

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
    global _runtime_initialized
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
        if os.path.isfile(ledger_store.DB_PATH):
            backup = ledger_store.create_backup(label='before_upgrade')
            get_logger().info('Created pre-upgrade database backup: %s', backup['path'])

        ledger_store.init_db()
        procurement_store.init_db()
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

# ── Create app instance ──
app = create_app()


def _shutdown():
    get_logger().info('Shutting down...')
    try:
        ledger_store.close_connections()
    except Exception:
        get_logger().warning('关闭数据库连接时出错', exc_info=True)
    close_logging()


def reset_runtime():
    """释放运行时资源，主要供测试 teardown 使用。"""
    global _runtime_initialized
    try:
        ledger_store.close_connections()
    except Exception:
        get_logger().debug('reset_runtime failed to close database connections', exc_info=True)
    close_logging()
    _runtime_initialized = False


def _signal_handler(signum, frame):
    _shutdown()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _open_browser_later(url):
    """Compatibility wrapper for delayed browser startup."""
    open_browser_later(url)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=app_config.HOST)
    parser.add_argument('--port', default=app_config.PORT, type=int)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if should_open_browser(args.no_browser, app_config.DEBUG):
        _open_browser_later(f'http://{args.host}:{args.port}/')
    try:
        app.run(debug=app_config.DEBUG, host=args.host, port=args.port)
    finally:
        _shutdown()
