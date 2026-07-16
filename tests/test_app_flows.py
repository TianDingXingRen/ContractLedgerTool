# -*- coding: utf-8 -*-
"""Route-level regression tests for the Flask contract tool."""

import io
import os
import tempfile
import unittest
import uuid
import zipfile
from unittest import mock

from docx import Document

import app
import template_def
from utils import helpers


def _docx_text(blob):
    doc = Document(io.BytesIO(blob))
    parts = []
    for paragraph in doc.paragraphs:
        parts.append(paragraph.text or '')
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(''.join(p.text or '' for p in cell.paragraphs))
    return '\n'.join(parts)


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_output = helpers.OUTPUT_FOLDER
        self.old_session = helpers.SESSION_FOLDER
        self.old_templates_dir = template_def.TEMPLATES_DIR
        self.old_create_ledger = helpers.create_ledger_record

        helpers.OUTPUT_FOLDER = os.path.join(self.tmp.name, 'output')
        helpers.SESSION_FOLDER = os.path.join(self.tmp.name, 'sessions')
        template_def.TEMPLATES_DIR = os.path.join(self.tmp.name, 'templates')
        os.makedirs(helpers.OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(helpers.SESSION_FOLDER, exist_ok=True)
        os.makedirs(template_def.TEMPLATES_DIR, exist_ok=True)
        helpers.create_ledger_record = lambda *args, **kwargs: None

        # 创建测试模板（无 source_docx，使用 generate_from_scratch）
        self._create_test_template()

    def tearDown(self):
        helpers.create_ledger_record = self.old_create_ledger
        helpers.OUTPUT_FOLDER = self.old_output
        helpers.SESSION_FOLDER = self.old_session
        template_def.TEMPLATES_DIR = self.old_templates_dir
        self.tmp.cleanup()

    def _create_test_template(self):
        """创建一个最小测试模板（无需源 DOCX 文件）。"""
        fields = [
            {
                'key': 'party_b',
                'label': '乙方',
                'field_type': 'text',
                'required': True,
                'location': {'type': 'paragraph', 'body_index': 0, 'placeholder': '{乙方}'},
            },
            {
                'key': 'contract_amount',
                'label': '合同金额',
                'field_type': 'text',
                'required': False,
                'location': {'type': 'paragraph', 'body_index': 1, 'placeholder': '{合同金额}'},
            },
        ]
        tpl = template_def.TemplateDef.create('测试模板', '', fields)
        self.test_template_path = tpl.save()
        self.test_tpl = tpl

    def test_batch_generation_from_scratch_template(self):
        """批量生成：使用无源文件的模板（generate_from_scratch 路径）。"""
        form = {
            'batch_counterparties': '测试甲公司\n测试乙公司',
        }
        for index, field in enumerate(self.test_tpl.data.get('fields', [])):
            fid = field.get('id', index)
            form[f'field_{fid}'] = f'测试值{fid}'

        sid = uuid.uuid4().hex
        helpers.save_session_data(sid, {
            'template_name': self.test_tpl.name,
            'template_path': self.test_template_path,
            'stored_name': '',
            'step': 'editor',
        })

        with app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['sid'] = sid
                sess['_csrf_token'] = 'test-token'
            form['csrf_token'] = 'test-token'
            response = client.post('/generate-batch', data=form)
            status_code = response.status_code
            response_body = response.get_data()
            response.close()

        self.assertEqual(status_code, 200, f'Expected 200, got {status_code}: {response_body[:300]}')
        with zipfile.ZipFile(io.BytesIO(response_body)) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 2)
            first_text = _docx_text(zf.read(names[0]))

        self.assertIn('测试甲公司', first_text)

    def test_batch_zip_failure_discards_created_contract(self):
        form = {'batch_counterparties': '测试甲公司'}
        for index, field in enumerate(self.test_tpl.data.get('fields', [])):
            fid = field.get('id', index)
            form[f'field_{fid}'] = f'测试值{fid}'

        sid = uuid.uuid4().hex
        helpers.save_session_data(sid, {
            'template_name': self.test_tpl.name,
            'template_path': self.test_template_path,
            'stored_name': '',
            'step': 'editor',
        })

        with app.app.test_client() as client, \
                mock.patch.object(helpers, 'create_ledger_record', return_value=123), \
                mock.patch('routes.contracts_bp.zipfile.ZipFile.write', side_effect=OSError('disk full')), \
                mock.patch('routes.contracts_bp._discard_generated_contract') as discard:
            with client.session_transaction() as sess:
                sess['sid'] = sid
                sess['_csrf_token'] = 'test-token'
            form['csrf_token'] = 'test-token'
            response = client.post('/generate-batch', data=form)

        self.assertEqual(response.status_code, 500)
        discard.assert_called_once()
        self.assertEqual(discard.call_args.args[0], 123)


if __name__ == '__main__':
    unittest.main()
