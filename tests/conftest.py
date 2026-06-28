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

    orig_base_dir = app_module.BASE_DIR
    orig_resource_dir = app_module.RESOURCE_DIR

    with tempfile.TemporaryDirectory() as tmp:
        test_app = app_module.create_app(
            runtime_base_dir=tmp,
            resource_dir=orig_resource_dir,
            run_maintenance=False,
            testing=True,
        )
        try:
            yield test_app
        finally:
            app_module.reset_runtime()

    app_module.configure_runtime_paths(orig_base_dir, orig_resource_dir)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tmp_db():
    """提供临时 SQLite 数据库的 fixture"""
    import ledger_store

    old_data_dir = ledger_store.DATA_DIR
    old_db_path = ledger_store.DB_PATH
    old_backup_dir = ledger_store.BACKUP_DIR

    with tempfile.TemporaryDirectory() as tmp:
        ledger_store.DATA_DIR = tmp
        ledger_store.DB_PATH = os.path.join(tmp, 'contracts.db')
        ledger_store.BACKUP_DIR = os.path.join(tmp, 'backups')
        ledger_store.init_db()
        yield tmp

    ledger_store.DATA_DIR = old_data_dir
    ledger_store.DB_PATH = old_db_path
    ledger_store.BACKUP_DIR = old_backup_dir
