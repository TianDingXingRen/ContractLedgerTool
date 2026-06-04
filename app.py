"""合同模板制作与生成工具 - Flask Web 应用"""

import os
import sys
import shutil
import uuid
import time
import signal
import argparse
import threading
import webbrowser

from flask import Flask, render_template, request, session, abort, jsonify

import template_def
import ledger_store
from utils import helpers
from utils.security import hmac_compare
from utils.logger import setup_logging, get_logger
from utils.errors import wants_json, api_error
from config import config as app_config

# ── Path resolution ──


def _runtime_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource_base_dir():
    return getattr(sys, '_MEIPASS', BASE_DIR)


BASE_DIR = _runtime_base_dir()
RESOURCE_DIR = _resource_base_dir()

# ── Directory setup ──

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')
SESSION_FOLDER = os.path.join(BASE_DIR, 'sessions')
template_def.TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
ledger_store.DATA_DIR = os.path.join(BASE_DIR, 'data')
ledger_store.DB_PATH = os.path.join(ledger_store.DATA_DIR, 'contracts.db')
ledger_store.BACKUP_DIR = os.path.join(ledger_store.DATA_DIR, 'backups')

_runtime_initialized = False

# ── Secret key persistence ──


def _load_or_create_secret_key():
    env_key = os.environ.get('CONTRACT_TOOL_SECRET_KEY')
    if env_key:
        return env_key
    key_file = os.path.join(BASE_DIR, '.secret_key')
    if os.path.exists(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    key = os.urandom(32).hex()
    with open(key_file, 'w', encoding='utf-8') as f:
        f.write(key)
    # 限制文件仅当前用户可读写（Windows 上设置为只读属性，防止意外修改）
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


# ── File cleanup ──

def _cleanup_old_files(max_age_days=None):
    """Remove files older than max_age_days from uploads/, output/, sessions/.

    Uses config OUTPUT_CLEANUP_DAYS for upload/output files and SESSION_TTL_HOURS for sessions.

    Preserves:
    - Output files referenced by ledger records (docx_path)
    - Uploaded DOCX files referenced by template definitions (source_docx)

    If the database is unavailable, cleanup is aborted to avoid data loss.
    """
    now = time.time()
    file_max_age_days = max_age_days if max_age_days is not None else app_config.OUTPUT_CLEANUP_DAYS
    cutoff = now - file_max_age_days * 86400

    preserved = set()
    try:
        docx_paths = ledger_store.get_all_docx_paths()
        for path in docx_paths:
            if path:
                preserved.add(os.path.normpath(os.path.abspath(path)))
    except Exception as e:
        get_logger().error('无法读取合同台账，跳过文件清理以避免数据丢失：%s', e)
        return

    # 保护模板引用中的上传源文件
    try:
        for tpl_info in template_def.list_templates():
            tpl_path = tpl_info.get('path', '')
            if not tpl_path or not os.path.isfile(tpl_path):
                continue
            try:
                tpl = template_def.TemplateDef.load(tpl_path)
                source_docx = tpl.data.get('source_docx', '')
                if source_docx:
                    src_path = os.path.join(UPLOAD_FOLDER, source_docx)
                    if os.path.isfile(src_path):
                        preserved.add(os.path.normpath(os.path.abspath(src_path)))
            except Exception:
                get_logger().warning('模板 %s 加载失败，upload 保护可能不完整', tpl_path, exc_info=True)
    except Exception as e:
        get_logger().warning('读取模板列表失败，upload 保护可能不完整：%s', e)

    for folder, label in [
        (UPLOAD_FOLDER, 'uploads'),
        (OUTPUT_FOLDER, 'output'),
    ]:
        try:
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                if not os.path.isfile(fpath):
                    continue
                if os.path.normpath(os.path.abspath(fpath)) in preserved:
                    continue
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    get_logger().info('Cleaned old %s file: %s', label, fname)
        except Exception as e:
            get_logger().warning('清理 %s 目录时出错：%s', label, e)

    # sessions 目录使用 SESSION_TTL_HOURS 配置的过期时间
    session_cutoff = now - app_config.SESSION_TTL_HOURS * 3600
    try:
        for fname in os.listdir(SESSION_FOLDER):
            fpath = os.path.join(SESSION_FOLDER, fname)
            if not os.path.isfile(fpath) or not fname.endswith('.json'):
                continue
            if os.path.getmtime(fpath) < session_cutoff:
                os.remove(fpath)
                get_logger().info('Cleaned old session file: %s', fname)
    except Exception as e:
        get_logger().warning('清理 sessions 目录时出错：%s', e)

_runtime_lock = threading.Lock()

def init_runtime(run_maintenance=True):
    """Initialize writable paths, logging, database, and packaged assets once.
    线程安全：通过 _runtime_lock 确保只初始化一次。"""
    global _runtime_initialized
    with _runtime_lock:
        if _runtime_initialized:
            return

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(SESSION_FOLDER, exist_ok=True)
        os.makedirs(template_def.TEMPLATES_DIR, exist_ok=True)

        # 首次运行时自动生成 config.json（如果不存在）
        from config import ensure_config_file
        ensure_config_file()

        helpers.UPLOAD_FOLDER = UPLOAD_FOLDER
        helpers.OUTPUT_FOLDER = OUTPUT_FOLDER
        helpers.SESSION_FOLDER = SESSION_FOLDER
        helpers.BASE_DIR = BASE_DIR

        # 初始化自启动模块的路径变量
        import utils.autostart as autostart
        autostart.BASE_DIR = BASE_DIR

        level = getattr(__import__('logging'), app_config.LOG_LEVEL.upper(), 20)
        setup_logging(os.path.join(BASE_DIR, 'logs'), level=level)

        ledger_store.init_db()
        if run_maintenance:
            ledger_store.backup_database()
            _cleanup_old_files(max_age_days=app_config.CLEANUP_DAYS)
        _seed_packaged_assets()
        _runtime_initialized = True

# ── Rate limiting ──
# 双层 LRU 限流器：
# 1. 全局 IP 维度：防路径绕过
# 2. 路径维度：精确控制高频接口

from collections import OrderedDict

_rate_limit_store_path = OrderedDict()
_rate_limit_store_global = OrderedDict()
_rate_limit_lock_path = threading.Lock()
_rate_limit_lock_global = threading.Lock()
_RATE_LIMIT_MAX_KEYS = 10000  # 最大条目数，超出时淘汰最旧条目


def _check_single_limit(store, lock, key, max_req, window, now):
    """单维度限流检查，返回 (allowed: bool, retry_seconds: int)"""
    with lock:
        while len(store) >= _RATE_LIMIT_MAX_KEYS:
            store.popitem(last=False)
        timestamps = store.get(key, [])
        timestamps[:] = [t for t in timestamps if t > now - window]
        if len(timestamps) >= max_req:
            retry = int(timestamps[0] + window - now) + 1
            return False, retry
        timestamps.append(now)
        store[key] = timestamps
        store.move_to_end(key)
    return True, 0


def _check_rate_limit():
    """双层限流：先检查全局 IP，再检查路径维度。返回 (allowed, retry_after_seconds)。"""
    path = request.path
    max_req, window = app_config.RATE_LIMITS.get(path, app_config.RATE_LIMIT_DEFAULT)
    ip = request.remote_addr or '127.0.0.1'
    now = time.time()

    # 第一层：全局 IP 限流（本地回环使用放宽阈值）
    if ip in ('127.0.0.1', '::1', 'localhost'):
        global_max, global_window = app_config.RATE_LIMIT_LOCALHOST
    else:
        global_max, global_window = app_config.RATE_LIMIT_GLOBAL
    global_allowed, global_retry = _check_single_limit(
        _rate_limit_store_global, _rate_limit_lock_global,
        ip, global_max, global_window, now,
    )
    if not global_allowed:
        return False, global_retry

    # 第二层：路径维度限流
    path_allowed, path_retry = _check_single_limit(
        _rate_limit_store_path, _rate_limit_lock_path,
        f'{ip}:{path}', max_req, window, now,
    )
    if not path_allowed:
        return False, path_retry

    return True, 0


# ── App factory ──


def create_app():
    init_runtime()
    app = Flask(
        __name__,
        template_folder=os.path.join(RESOURCE_DIR, 'templates'),
        static_folder=os.path.join(RESOURCE_DIR, 'static'),
    )
    app.secret_key = _load_or_create_secret_key()
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['MAX_CONTENT_LENGTH'] = app_config.MAX_CONTENT_LENGTH_MB * 1024 * 1024

    # ── CSRF + rate limit ──
    @app.before_request
    def _protect_post_requests():
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            expected = session.get('_csrf_token')
            provided = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not expected or not provided or not hmac_compare(expected, provided):
                abort(400, description='CSRF token missing or invalid')
            allowed, retry = _check_rate_limit()
            if not allowed:
                if wants_json():
                    return api_error('请求过于频繁，请稍后再试', 429)
                abort(429, description=f'请求过于频繁，请 {retry} 秒后再试')
        return None

    # ── Template globals ──
    @app.context_processor
    def inject_label_maps():
        return {
            'contract_status_labels': helpers.CONTRACT_STATUS_LABELS,
            'confirm_status_labels': helpers.CONFIRM_STATUS_LABELS,
            'payment_status_labels': helpers.PAYMENT_STATUS_LABELS,
            'confidence_labels': helpers.CONFIDENCE_LABELS,
            'csrf_token': _csrf_token,
        }

    # ── Register routes ──
    from routes import register_all
    register_all(app)

    # ── Global error handlers ──

    @app.errorhandler(400)
    def handle_400(e):
        msg = getattr(e, 'description', None) or '请求参数无效'
        if wants_json():
            return api_error(str(msg), 400)
        return render_template('error.html', code=400, message=str(msg)), 400

    @app.errorhandler(404)
    def handle_404(e):
        msg = getattr(e, 'description', None) or '页面未找到'
        if wants_json():
            return api_error(str(msg), 404)
        return render_template('error.html', code=404, message=str(msg)), 404

    @app.errorhandler(429)
    def handle_429(e):
        msg = getattr(e, 'description', None) or '请求过于频繁'
        if wants_json():
            return api_error(str(msg), 429)
        return render_template('error.html', code=429, message=str(msg)), 429

    @app.errorhandler(500)
    def handle_500(e):
        get_logger().error('Internal server error: %s', e, exc_info=True)
        if wants_json():
            return api_error('服务器内部错误', 500)
        return render_template('error.html', code=500, message='服务器内部错误，请稍后再试'), 500

    _error_handler_guard = threading.local()

    @app.errorhandler(Exception)
    def handle_unhandled(e):
        # 防护递归：如果 error.html 模板渲染本身出错，返回纯文本
        if getattr(_error_handler_guard, 'active', False):
            return '500 Internal Server Error', 500
        _error_handler_guard.active = True
        try:
            get_logger().error('Unhandled exception: %s', e, exc_info=True)
            if wants_json():
                return api_error('服务器内部错误', 500)
            return render_template('error.html', code=500, message='服务器内部错误，请稍后再试'), 500
        finally:
            _error_handler_guard.active = False

    return app


def _csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = uuid.uuid4().hex
        session['_csrf_token'] = token
    return token


def _seed_packaged_assets():
    """Copy bundled templates, uploads, and launcher scripts from resource dir to writable dir.

    使用版本标记机制：打包版本号与已安装版本号相同时跳过，
    版本不同时只覆盖打包自带文件，不覆盖用户自建文件。
    """
    if os.path.abspath(RESOURCE_DIR) == os.path.abspath(BASE_DIR):
        return

    # 读取打包版本号
    version_file = os.path.join(RESOURCE_DIR, 'version.txt')
    current_version = ''
    if os.path.isfile(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            current_version = f.read().strip()

    # 读取已安装版本号
    installed_version_file = os.path.join(BASE_DIR, '.installed_version')
    installed_version = ''
    if os.path.isfile(installed_version_file):
        with open(installed_version_file, 'r', encoding='utf-8') as f:
            installed_version = f.read().strip()

    # 版本相同，无需更新
    if current_version and current_version == installed_version:
        return

    # 收集打包自带文件清单（用于判断是否可覆盖）
    packaged_files = set()
    resource_templates = os.path.join(RESOURCE_DIR, 'templates')
    if os.path.isdir(resource_templates):
        for fname in os.listdir(resource_templates):
            if fname.endswith('.contract-template'):
                packaged_files.add(fname)
                src = os.path.join(resource_templates, fname)
                dst = os.path.join(template_def.TEMPLATES_DIR, fname)
                # 首次安装或打包自带文件，直接覆盖
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

    resource_uploads = os.path.join(RESOURCE_DIR, 'uploads')
    if os.path.isdir(resource_uploads):
        for fname in os.listdir(resource_uploads):
            src = os.path.join(resource_uploads, fname)
            dst = os.path.join(UPLOAD_FOLDER, fname)
            if os.path.isfile(src):
                packaged_files.add(fname)
                if not os.path.exists(dst) or fname in packaged_files:
                    shutil.copy2(src, dst)

    # 复制 start.ps1 / stop.ps1 到 BASE_DIR（自启动需要）
    _seed_launcher_script(RESOURCE_DIR, BASE_DIR, 'start.ps1')
    _seed_launcher_script(RESOURCE_DIR, BASE_DIR, 'stop.ps1')

    # 写入新版本标记
    if current_version:
        with open(installed_version_file, 'w', encoding='utf-8') as f:
            f.write(current_version)


def _seed_launcher_script(resource_dir, target_dir, filename):
    """Copy a single launcher script from resource dir to target dir."""
    # 尝试多个可能的位置
    candidates = [
        os.path.join(resource_dir, 'installer_assets', filename),
        os.path.join(resource_dir, filename),
    ]
    dst = os.path.join(target_dir, filename)
    if os.path.exists(dst):
        return
    for src in candidates:
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            return

# ── Create app instance ──
app = create_app()


def _shutdown():
    get_logger().info('Shutting down...')
    try:
        ledger_store.close_connections()
    except Exception:
        get_logger().warning('关闭数据库连接时出错', exc_info=True)


def _signal_handler(signum, frame):
    _shutdown()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _open_browser_later(url):
    def opener():
        try:
            webbrowser.open(url)
        except Exception:
            get_logger().debug('自动打开浏览器失败', exc_info=True)
    threading.Timer(1.0, opener).start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=app_config.HOST)
    parser.add_argument('--port', default=app_config.PORT, type=int)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not args.no_browser:
        _open_browser_later(f'http://{args.host}:{args.port}/')
    try:
        app.run(debug=app_config.DEBUG, host=args.host, port=args.port)
    finally:
        _shutdown()
