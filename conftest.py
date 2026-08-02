"""全项目 pytest 引导：确保导入 app 时不会读写真实运行数据。

创建隔离运行时目录并设置 CONTRACT_TOOL_RUNTIME_DIR。通过 atexit + 信号
处理兜底清理，避免进程被中断或异常退出时残留临时目录。
"""

import atexit
import os
import shutil
import signal
import stat
import sys
import tempfile

import pytest

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEST_RUNTIME = tempfile.mkdtemp(prefix='.pytest_runtime_', dir=_BASE_DIR)
os.environ['CONTRACT_TOOL_RUNTIME_DIR'] = _TEST_RUNTIME

_FAST_TEST_MODULES = {
    'test_app_errors.py',
    'test_app_secrets.py',
    'test_app_startup.py',
    'test_app_template_context.py',
    'test_cn_money.py',
    'test_contract_preview.py',
    'test_docs_index.py',
    'test_editor_js.py',
    'test_field_eval.py',
    'test_frontend_assets.py',
    'test_ledger_document_paths.py',
    'test_ledger_money_fields.py',
    'test_payment_extractor.py',
    'test_payment_extractor_advanced.py',
    'test_security.py',
}
_PACKAGING_TEST_MODULES = {
    'test_demo_data_entrypoint.py',
    'test_dependency_lock.py',
    'test_installer_rollback.py',
    'test_packaged_self_check.py',
    'test_release_engineering.py',
    'test_worktree_scope.py',
}


def pytest_collection_modifyitems(items):
    """Assign every test to a stable delivery tier without test-order coupling."""
    for item in items:
        filename = os.path.basename(str(item.path))
        if filename == 'test_ui_playwright.py':
            item.add_marker(pytest.mark.ui)
        elif filename in _PACKAGING_TEST_MODULES:
            item.add_marker(pytest.mark.packaging)
        elif filename in _FAST_TEST_MODULES:
            item.add_marker(pytest.mark.fast)
        else:
            item.add_marker(pytest.mark.integration)


def _force_rmtree(path):
    """递归清除只读属性后删除目录，兼容 Windows。"""
    def _on_rm_error(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except Exception:
            pass
    shutil.rmtree(path, onerror=_on_rm_error)


def _cleanup():
    app_module = sys.modules.get('app')
    if app_module is not None:
        try:
            app_module.reset_runtime()
        except Exception:
            pass
    _cleanup_done = globals().setdefault('_cleaned', False)
    if _cleanup_done:
        return
    globals()['_cleaned'] = True
    _force_rmtree(_TEST_RUNTIME)
    os.environ.pop('CONTRACT_TOOL_RUNTIME_DIR', None)


def _cleanup_on_signal(signum, frame):
    _cleanup()
    sys.exit(128 + signum)


atexit.register(_cleanup)
for _sig in (signal.SIGINT, signal.SIGTERM, signal.SIGBREAK):
    try:
        signal.signal(_sig, _cleanup_on_signal)
    except (OSError, ValueError):
        pass


def pytest_sessionfinish(session, exitstatus):
    _cleanup()
