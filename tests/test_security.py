# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from docx import Document

import app
import field_eval
import ledger_store
from routes import contracts_bp
from utils import helpers
from utils import autostart


class SecurityHardeningTests(unittest.TestCase):
    def test_formula_rejects_power_operator(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('9 ** 9')

    def test_validate_formula_rejects_power_operator(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.validate_formula('9 ** 9')

    def test_calculated_field_rejects_missing_dependency(self):
        fields = [{
            'key': 'total',
            'label': '合计',
            'field_type': 'calculated',
            'formula': 'qty * price',
        }]
        with self.assertRaises(field_eval.FormulaError):
            field_eval.sort_fields_by_dependency(fields)

    def test_formula_rejects_overlong_expression(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('1+' * 300 + '1')

    def test_payment_plan_update_is_scoped_to_contract(self):
        old_data_dir = ledger_store.DATA_DIR
        old_db_path = ledger_store.DB_PATH
        self.addCleanup(setattr, ledger_store, 'DATA_DIR', old_data_dir)
        self.addCleanup(setattr, ledger_store, 'DB_PATH', old_db_path)
        with tempfile.TemporaryDirectory() as tmp:
            ledger_store.DATA_DIR = tmp
            ledger_store.DB_PATH = os.path.join(tmp, 'contracts.db')
            ledger_store.init_db()
            contract_a = ledger_store.create_contract({'title': 'A'}, {}, os.path.join(tmp, 'a.docx'))
            contract_b = ledger_store.create_contract({'title': 'B'}, {}, os.path.join(tmp, 'b.docx'))
            plan_id = ledger_store.insert_payment_plan(contract_a, {'phase_name': '首付款'})

            self.assertEqual(
                ledger_store.update_payment_plan(plan_id, {'phase_name': '错误修改'}, contract_id=contract_b),
                0,
            )
            self.assertEqual(
                ledger_store.update_payment_plan(plan_id, {'phase_name': '正确修改'}, contract_id=contract_a),
                1,
            )
            plan = ledger_store.list_payment_plans(contract_id=contract_a)[0]
            self.assertEqual(plan['phase_name'], '正确修改')

    def test_database_rejects_invalid_status_and_orphan_payment(self):
        old_data_dir = ledger_store.DATA_DIR
        old_db_path = ledger_store.DB_PATH
        self.addCleanup(setattr, ledger_store, 'DATA_DIR', old_data_dir)
        self.addCleanup(setattr, ledger_store, 'DB_PATH', old_db_path)
        with tempfile.TemporaryDirectory() as tmp:
            ledger_store.DATA_DIR = tmp
            ledger_store.DB_PATH = os.path.join(tmp, 'contracts.db')
            ledger_store.init_db()
            with self.assertRaises(ValueError):
                ledger_store.create_contract({'title': 'A', 'status': 'bad'}, {}, os.path.join(tmp, 'a.docx'))
            with self.assertRaises(sqlite3.IntegrityError):
                ledger_store.insert_payment_plan(9999, {'phase_name': '孤立计划'})

    def test_template_source_binding_preflight_reports_missing_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = os.path.join(tmp, 'source.docx')
            doc = Document()
            doc.add_paragraph('甲方：{甲方}')
            doc.save(docx_path)
            errors = helpers.validate_template_source_bindings([
                {
                    'key': 'party_b',
                    'label': '乙方',
                    'field_type': 'text',
                    'location': {'type': 'paragraph', 'body_index': 0, 'placeholder': '{乙方}'},
                }
            ], docx_path)
            self.assertTrue(errors)
            self.assertIn('乙方', errors[0])

    def test_pdf_download_sanitizes_contract_number_path(self):
        old_output = helpers.OUTPUT_FOLDER
        self.addCleanup(setattr, helpers, 'OUTPUT_FOLDER', old_output)
        with tempfile.TemporaryDirectory() as tmp:
            helpers.OUTPUT_FOLDER = tmp
            docx_path = os.path.join(tmp, 'source.docx')
            with open(docx_path, 'wb') as f:
                f.write(b'docx')
            written_paths = []

            def fake_convert(_docx_path, pdf_path):
                written_paths.append(pdf_path)
                with open(pdf_path, 'wb') as f:
                    f.write(b'%PDF-1.4\n')

            contract = {'docx_path': docx_path, 'contract_no': '..\\outside/name'}
            with mock.patch.object(ledger_store, 'get_contract', return_value=contract), \
                    mock.patch.object(contracts_bp.pdf_exporter, 'convert_docx_to_pdf', side_effect=fake_convert):
                with app.app.test_client() as client:
                    response = client.get('/contracts/1/download-pdf')
                    try:
                        self.assertEqual(response.status_code, 200)
                    finally:
                        response.close()

            self.assertEqual(len(written_paths), 1)
            self.assertTrue(helpers.path_within(tmp, written_paths[0]))
            self.assertNotIn('..', os.path.basename(written_paths[0]))

    def test_post_without_csrf_is_rejected(self):
        with app.app.test_client() as client:
            response = client.post('/template/manual-save', data={'template_name': 'x'})
            try:
                self.assertEqual(response.status_code, 400)
            finally:
                response.close()

    def test_csp_does_not_allow_unsafe_eval(self):
        with app.app.test_client() as client:
            response = client.get('/')
            try:
                csp = response.headers.get('Content-Security-Policy', '')
                self.assertIn("script-src 'self'", csp)
                self.assertNotIn("'unsafe-eval'", csp)
            finally:
                response.close()

    def test_manual_template_rejects_source_docx_path_traversal(self):
        form = {
            'csrf_token': 'token',
            'template_name': 'safe-template',
            'stored_name': '..\\secret.docx',
            'field_label_0': '甲方',
            'field_type_0': 'text',
        }
        with app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_csrf_token'] = 'token'
            response = client.post('/template/manual-save', data=form)
            try:
                self.assertEqual(response.status_code, 400)
                self.assertIn('文件名无效', response.get_data(as_text=True))
            finally:
                response.close()

    def test_enable_autostart_registers_current_app_command(self):
        completed = mock.Mock(returncode=0, stdout='Ready', stderr='')
        with mock.patch.object(os, 'name', 'nt'), \
                mock.patch.object(autostart, '_run_powershell', return_value=completed) as run, \
                mock.patch.object(autostart, '_remove_legacy_startup_launchers'):
            helpers.enable_autostart()

        script = run.call_args_list[0].args[0]
        self.assertIn('New-ScheduledTaskAction', script)
        self.assertIn('Register-ScheduledTask', script)
        self.assertTrue('--no-browser' in script or '-NoBrowser' in script)

    def test_autostart_powershell_runs_without_console_window(self):
        completed = mock.Mock(returncode=0, stdout='', stderr='')
        with mock.patch.object(
                autostart.subprocess, 'run', return_value=completed) as run:
            result = autostart._run_powershell('Write-Output ready')

        self.assertIs(result, completed)
        kwargs = run.call_args.kwargs
        self.assertTrue(
            kwargs['creationflags'] & autostart.subprocess.CREATE_NO_WINDOW
        )
        self.assertTrue(
            kwargs['startupinfo'].dwFlags
            & autostart.subprocess.STARTF_USESHOWWINDOW
        )
        self.assertEqual(
            kwargs['startupinfo'].wShowWindow,
            autostart.subprocess.SW_HIDE,
        )

    def test_enable_autostart_fallback_rewrites_startup_launcher(self):
        autostart._autostart_cache = None
        completed = mock.Mock(returncode=1, stdout='', stderr='denied')
        with tempfile.TemporaryDirectory() as tmp:
            legacy_path = os.path.join(tmp, 'ContractLedgerTool.vbs')
            with open(legacy_path, 'w', encoding='utf-8') as f:
                f.write('WScript.Echo "broken"')

            with mock.patch.object(os, 'name', 'nt'), \
                    mock.patch.object(autostart, '_run_powershell', return_value=completed), \
                    mock.patch.object(autostart, '_startup_folder', return_value=tmp):
                source = helpers.enable_autostart()

            launcher_path = os.path.join(tmp, helpers.AUTOSTART_LAUNCHER_NAME)
            self.assertEqual(source, 'startup')
            self.assertFalse(os.path.exists(legacy_path))
            self.assertTrue(os.path.isfile(launcher_path))
            with open(launcher_path, 'rb') as f:
                self.assertEqual(f.read(2), b'\xff\xfe')
            with open(launcher_path, 'r', encoding='utf-16') as f:
                content = f.read()
            self.assertIn('shell.CurrentDirectory', content)
            self.assertTrue('--no-browser' in content or '-NoBrowser' in content)
            self.assertTrue(autostart._startup_launcher_matches(launcher_path))

    def test_autostart_disabled_task_is_not_enabled(self):
        autostart._autostart_cache = None
        completed = mock.Mock(returncode=0, stdout='Disabled\n', stderr='')
        with mock.patch.object(os, 'name', 'nt'), \
                mock.patch.object(autostart, '_run_powershell', return_value=completed), \
                mock.patch.object(autostart, '_startup_launcher_path', return_value='Z:\\missing.vbs'), \
                mock.patch.object(autostart, '_legacy_startup_launcher_paths', return_value=[]):
            status = helpers.autostart_status()
        self.assertFalse(status['enabled'])
        self.assertEqual(status['task_state'], 'Disabled')

    def test_index_defers_autostart_status_query(self):
        with mock.patch.object(
                helpers, 'autostart_status',
                side_effect=AssertionError('首页不应同步查询 PowerShell 状态')):
            with app.app.test_client() as client:
                response = client.get('/')
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('检测中', response.get_data(as_text=True))
                finally:
                    response.close()

    def test_autostart_status_api_returns_json(self):
        status = {
            'enabled': True,
            'supported': True,
            'description': '计划任务已启用',
            'source': '计划任务',
        }
        with mock.patch.object(helpers, 'autostart_status', return_value=status):
            with app.app.test_client() as client:
                response = client.get('/api/autostart/status')
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.get_json()['enabled'])
                finally:
                    response.close()

    def test_diagnostics_routes_load(self):
        with app.app.test_client() as client:
            with mock.patch.object(
                    helpers, 'autostart_status',
                    side_effect=AssertionError('诊断页不应同步查询 PowerShell 状态')):
                html_response = client.get('/diagnostics')
            with mock.patch.object(helpers, 'autostart_status', return_value={
                    'enabled': False,
                    'supported': True,
                    'description': '未开启',
                    'task_state': '',
                    'startup_path': '',
                    'message': '',
            }):
                json_response = client.get('/api/diagnostics')
            try:
                self.assertEqual(html_response.status_code, 200)
                self.assertEqual(json_response.status_code, 200)
                self.assertIn('autostart', json_response.get_json())
            finally:
                html_response.close()
                json_response.close()


if __name__ == '__main__':
    unittest.main()
