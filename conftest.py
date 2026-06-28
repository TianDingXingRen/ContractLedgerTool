"""全项目 pytest 引导：确保导入 app 时不会读写真实运行数据。"""

import os
import shutil
import sys
import tempfile


_TEST_RUNTIME = tempfile.mkdtemp(
    prefix='.pytest_runtime_',
    dir=os.path.dirname(os.path.abspath(__file__)),
)
os.environ['CONTRACT_TOOL_RUNTIME_DIR'] = _TEST_RUNTIME


def pytest_sessionfinish(session, exitstatus):
    app_module = sys.modules.get('app')
    if app_module is not None:
        try:
            app_module.reset_runtime()
        except Exception:
            pass
    shutil.rmtree(_TEST_RUNTIME, ignore_errors=True)
    os.environ.pop('CONTRACT_TOOL_RUNTIME_DIR', None)
