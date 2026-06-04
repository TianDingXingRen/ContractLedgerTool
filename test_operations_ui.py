# -*- coding: utf-8 -*-
"""Regression tests for diagnostics, backups, and editor UI affordances."""

import os
import json
import tempfile
import unittest
from unittest import mock

import app
import ledger_store
import template_def
from utils import helpers


class OperationsUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = ledger_store.DATA_DIR
        self.old_db_path = ledger_store.DB_PATH
        self.old_backup_dir = ledger_store.BACKUP_DIR
        self.old_session_folder = helpers.SESSION_FOLDER
        self.old_output_folder = helpers.OUTPUT_FOLDER
        self.old_templates_dir = template_def.TEMPLATES_DIR

        ledger_store.DATA_DIR = os.path.join(self.tmp.name, 'data')
        ledger_store.DB_PATH = os.path.join(ledger_store.DATA_DIR, 'contracts.db')
        ledger_store.BACKUP_DIR = os.path.join(ledger_store.DATA_DIR, 'backups')
        helpers.SESSION_FOLDER = os.path.join(self.tmp.name, 'sessions')
        helpers.OUTPUT_FOLDER = os.path.join(self.tmp.name, 'output')
        template_def.TEMPLATES_DIR = os.path.join(self.tmp.name, 'templates')

        os.makedirs(helpers.SESSION_FOLDER, exist_ok=True)
        os.makedirs(helpers.OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(template_def.TEMPLATES_DIR, exist_ok=True)
        ledger_store.init_db()
        ledger_store.run_migrations()

    def tearDown(self):
        ledger_store.DATA_DIR = self.old_data_dir
        ledger_store.DB_PATH = self.old_db_path
        ledger_store.BACKUP_DIR = self.old_backup_dir
        helpers.SESSION_FOLDER = self.old_session_folder
        helpers.OUTPUT_FOLDER = self.old_output_folder
        template_def.TEMPLATES_DIR = self.old_templates_dir
        self.tmp.cleanup()

    def _client_with_csrf(self):
        client = app.app.test_client()
        with client.session_transaction() as sess:
            sess['_csrf_token'] = 'test-token'
        return client

    def test_backup_create_download_restore_routes(self):
        first_docx = os.path.join(self.tmp.name, 'first.docx')
        second_docx = os.path.join(self.tmp.name, 'second.docx')
        open(first_docx, 'wb').close()
        open(second_docx, 'wb').close()

        ledger_store.create_contract({'title': '第一份合同'}, {}, first_docx)
        with self._client_with_csrf() as client:
            response = client.post(
                '/backups/create',
                data={'csrf_token': 'test-token'},
                headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            )
            try:
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                payload = response.get_json()
            finally:
                response.close()

            filename = payload['backup']['filename']
            self.assertTrue(filename.endswith('.db'))
            self.assertTrue(os.path.exists(os.path.join(ledger_store.BACKUP_DIR, filename)))

            ledger_store.create_contract({'title': '第二份合同'}, {}, second_docx)
            self.assertEqual(ledger_store.get_contract_stats()['total'], 2)

            restore_response = client.post(
                f'/backups/{filename}/restore',
                data={'csrf_token': 'test-token'},
                headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
            )
            try:
                self.assertEqual(restore_response.status_code, 200, restore_response.get_data(as_text=True))
            finally:
                restore_response.close()

            self.assertEqual(ledger_store.get_contract_stats()['total'], 1)

            download_response = client.get(f'/backups/{filename}/download')
            try:
                self.assertEqual(download_response.status_code, 200)
                self.assertGreater(len(download_response.get_data()), 0)
            finally:
                download_response.close()

    def test_backup_download_rejects_unknown_file(self):
        with app.app.test_client() as client:
            response = client.get('/backups/not-a-backup.txt/download')
            try:
                self.assertEqual(response.status_code, 404)
            finally:
                response.close()

    def test_diagnostics_open_folder_uses_whitelisted_paths(self):
        with self._client_with_csrf() as client:
            with mock.patch('routes.settings_bp._open_folder') as open_folder:
                response = client.post(
                    '/diagnostics/open-folder',
                    data={'folder': 'backups', 'csrf_token': 'test-token'},
                    headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
                )
                try:
                    self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                    payload = response.get_json()
                finally:
                    response.close()

                self.assertTrue(payload['success'])
                self.assertEqual(os.path.abspath(payload['path']), os.path.abspath(ledger_store.BACKUP_DIR))
                open_folder.assert_called_once()

                invalid = client.post(
                    '/diagnostics/open-folder',
                    data={'folder': 'windows', 'csrf_token': 'test-token'},
                    headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
                )
                try:
                    self.assertEqual(invalid.status_code, 400)
                    self.assertFalse(invalid.get_json()['success'])
                finally:
                    invalid.close()

    def test_diagnostics_page_exposes_one_click_actions(self):
        with app.app.test_client() as client:
            response = client.get('/diagnostics')
            try:
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
            finally:
                response.close()

        self.assertIn('data-testid="copy-diagnostics"', html)
        self.assertIn('data-testid="refresh-diagnostics"', html)
        self.assertIn('/diagnostics/open-folder', html)
        self.assertIn('diagnostics-folder-form', html)
        self.assertIn('/backups', html)

    def test_editor_page_exposes_sidebar_filters_and_result_panel(self):
        sid = 'editor-ui-test'
        helpers.save_session_data(sid, {
            'template_name': '测试模板',
            'step': 'editor',
            'fields': [
                {'id': 1, 'key': 'party_a', 'label': '甲方', 'field_type': 'text', 'required': True},
                {'id': 2, 'key': 'total', 'label': '合计', 'field_type': 'calculated', 'formula': '1 + 1'},
                {
                    'id': 3,
                    'key': 'items',
                    'label': '明细',
                    'field_type': 'table',
                    'columns': [{'key': 'name', 'label': '名称'}],
                    'default_rows': [],
                },
            ],
        })

        with app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['sid'] = sid
            response = client.get('/editor')
            try:
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
            finally:
                response.close()

        self.assertIn('data-testid="editor-sidebar"', html)
        self.assertIn('id="fieldNavigator"', html)
        self.assertIn('data-filter="required"', html)
        self.assertIn('data-filter="calc"', html)
        self.assertIn('data-testid="generation-result"', html)
        self.assertIn('function showGenerationResult', html)
        self.assertNotIn('window.location.href = result.detailUrl', html)

    def test_create_template_table_editor_uses_stacked_column_cards(self):
        with app.app.test_client() as client:
            response = client.get('/create-template')
            try:
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
            finally:
                response.close()

        self.assertIn('col-default-wrap', html)
        self.assertIn('col-formula-wrap', html)
        self.assertIn('refreshColumnRemoveButtons', html)
        self.assertNotIn('max-w-2xl', html)

    def test_builder_preview_expands_with_page(self):
        with app.app.test_client() as client:
            response = client.get('/create-template')
            try:
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
            finally:
                response.close()

        self.assertIn('编制模板', html)

    def test_manual_template_save_preserves_table_column_types(self):
        form = {
            'csrf_token': 'test-token',
            'template_name': '表格测试模板',
            'stored_name': '',
            'field_label_0': '明细表',
            'field_key_0': 'items',
            'field_type_0': 'table',
            'field_required_0': 'on',
            'col_label_0_0': '产品名称',
            'col_type_0_0': 'text',
            'col_default_0_0': '标准产品',
            'col_label_0_1': '数量',
            'col_type_0_1': 'text',
            'col_label_0_2': '单价',
            'col_type_0_2': 'text',
            'col_label_0_3': '小计',
            'col_type_0_3': 'calculated',
            'col_formula_0_3': 'qty * unit_price',
            'col_default_0_3': 'should be ignored',
        }
        with self._client_with_csrf() as client:
            response = client.post('/template/manual-save', data=form)
            try:
                self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
            finally:
                response.close()

        files = os.listdir(template_def.TEMPLATES_DIR)
        self.assertEqual(len(files), 1)
        with open(os.path.join(template_def.TEMPLATES_DIR, files[0]), 'r', encoding='utf-8') as f:
            data = json.load(f)

        columns = data['fields'][0]['columns']
        self.assertEqual(columns[0]['default_value'], '标准产品')
        self.assertEqual(columns[1]['key'], 'qty')
        self.assertEqual(columns[2]['key'], 'unit_price')
        self.assertEqual(columns[3]['field_type'], 'calculated')
        self.assertEqual(columns[3]['formula'], 'qty * unit_price')
        self.assertEqual(columns[3]['default_value'], '')


if __name__ == '__main__':
    unittest.main()
