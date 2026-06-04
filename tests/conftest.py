"""测试框架 fixture — 提供隔离的 Flask app 客户端和临时数据库"""

import os
import sys
import tempfile

import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """创建测试用 Flask app，使用临时目录隔离"""
    import app as app_module

    # 保存原始值
    orig_base_dir = getattr(app_module, 'BASE_DIR', None)
    orig_upload = getattr(app_module, 'UPLOAD_FOLDER', None)
    orig_output = getattr(app_module, 'OUTPUT_FOLDER', None)
    orig_session = getattr(app_module, 'SESSION_FOLDER', None)

    with tempfile.TemporaryDirectory() as tmp:
        app_module.BASE_DIR = tmp
        app_module.UPLOAD_FOLDER = os.path.join(tmp, 'uploads')
        app_module.OUTPUT_FOLDER = os.path.join(tmp, 'output')
        app_module.SESSION_FOLDER = os.path.join(tmp, 'sessions')
        app_module._runtime_initialized = False
        for d in (app_module.UPLOAD_FOLDER, app_module.OUTPUT_FOLDER,
                  app_module.SESSION_FOLDER):
            os.makedirs(d, exist_ok=True)

        test_app = app_module.create_app()
        test_app.config['TESTING'] = True
        yield test_app

    # 恢复原始值
    if orig_base_dir is not None:
        app_module.BASE_DIR = orig_base_dir
        app_module.UPLOAD_FOLDER = orig_upload
        app_module.OUTPUT_FOLDER = orig_output
        app_module.SESSION_FOLDER = orig_session


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tmp_db():
    """提供临时 SQLite 数据库的 fixture"""
    import ledger_store

    old_data_dir = ledger_store.DATA_DIR
    old_db_path = ledger_store.DB_PATH

    with tempfile.TemporaryDirectory() as tmp:
        ledger_store.DATA_DIR = tmp
        ledger_store.DB_PATH = os.path.join(tmp, 'contracts.db')
        ledger_store.init_db()
        yield tmp

    ledger_store.DATA_DIR = old_data_dir
    ledger_store.DB_PATH = old_db_path
