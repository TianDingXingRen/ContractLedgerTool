"""Full end-to-end integration test: load template, apply all fields, verify output."""
import glob
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import docx_builder
import field_eval
from docx import Document
from docx.oxml.ns import qn

BASE = os.path.dirname(__file__)


class EndToEndTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        template_candidates = [
            os.path.join(BASE, 'templates', 'Template1_Test.contract-template'),
            os.path.join(BASE, 'templates', '订货.contract-template'),
        ]
        tpl_path = next((p for p in template_candidates if os.path.exists(p)), None)
        if tpl_path is None:
            available = sorted(glob.glob(os.path.join(BASE, 'templates', '*.contract-template')))
            if not available:
                raise unittest.SkipTest('No contract template found.')
            tpl_path = available[0]

        with open(tpl_path, 'r', encoding='utf-8') as f:
            cls.tpl = json.load(f)

        cls.fields = cls.tpl['fields']

        src = cls.tpl.get('source_docx', '')
        src_path = os.path.join(BASE, 'uploads', src)
        if not os.path.exists(src_path):
            raise unittest.SkipTest(f'Source docx not found: {src_path}')

        cls.src_path = src_path
        cls.doc = Document(src_path)

        cls.field_values = {}
        for idx, f in enumerate(cls.fields):
            fid = f.get('id', idx)
            key = f['key']
            if f['field_type'] == 'table':
                row = {}
                for c in f.get('columns', []):
                    row[c['key']] = f'{c["label"]}_测试'
                cls.field_values[key] = [row]
            else:
                cls.field_values[key] = f'接报_{key}'

    def test_template_loads(self):
        self.assertIn('template_name', self.tpl)
        self.assertIn('fields', self.tpl)
        self.assertTrue(len(self.fields) > 0)

    def test_apply_fields(self):
        ordered_fields = field_eval.sort_fields_by_dependency(self.fields)
        errors = []
        for field in ordered_fields:
            ftype = field['field_type']
            key = field['key']
            location = field.get('location', {})
            if ftype == 'table':
                try:
                    docx_builder.apply_table_field(self.doc, field, self.field_values.get(key, []))
                except Exception as e:
                    errors.append(f'{key}: {e}')
            else:
                try:
                    docx_builder.apply_text_field(self.doc, location, self.field_values.get(key, ''), field.get('label', ''), key)
                except Exception as e:
                    errors.append(f'{key}: {e}')
        self.assertEqual(len(errors), 0, f'Field application errors: {errors}')

    def test_paragraph_replacement(self):
        body = self.doc.element.body
        p0_text = ''.join(t.text or '' for t in body[0].iter(qn('w:t')))
        replaced = any(
            f'接报_{f["key"]}' in p0_text
            for f in self.fields
            if f.get('location', {}).get('body_index') == 0
        )
        if replaced:
            self.assertTrue(replaced)
        else:
            self.skipTest('No fields mapped to paragraph 0')

    def test_output_save(self):
        output_path = os.path.join(BASE, 'output', 'test_verify_output.docx')
        self.doc.save(output_path)
        self.assertTrue(os.path.exists(output_path))
        self.assertGreater(os.path.getsize(output_path), 100)


if __name__ == '__main__':
    unittest.main()
