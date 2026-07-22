import os
import sqlite3

import app
from ledger_store import schema as ledger_schema
from procurement_store import schema as procurement_schema


def test_self_check_uses_isolated_runtime(tmp_path):
    runtime_dir = tmp_path / 'isolated-runtime'
    report_path = tmp_path / 'self-check.json'

    assert app.run_self_check(str(runtime_dir), str(report_path)) is True
    report = report_path.read_text(encoding='utf-8')
    assert '"ok": true' in report
    assert '"http_status": 200' in report
    assert os.path.isfile(runtime_dir / 'data' / 'contracts.db')
    with sqlite3.connect(runtime_dir / 'data' / 'contracts.db') as conn:
        ledger_version = conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
        procurement_version = conn.execute(
            'SELECT MAX(version) FROM procurement_schema_version'
        ).fetchone()[0]
    assert ledger_version == ledger_schema.CURRENT_SCHEMA_VERSION
    assert procurement_version == procurement_schema.CURRENT_SCHEMA_VERSION
