import os
import shutil
import subprocess
import unittest

import app


class EditorJavaScriptTests(unittest.TestCase):
    def test_editor_script_has_valid_syntax(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')

        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js')
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
        result = subprocess.run(
            [node, '--check', '-'],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_editor_script_exposes_inline_event_handlers(self):
        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js')
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        start = script.find('Object.assign(window,')
        self.assertNotEqual(start, -1, 'editor.js must expose handlers used by inline HTML events')
        end = script.find('});', start)
        self.assertNotEqual(end, -1, 'window handler export block is incomplete')
        exports_block = script[start:end]

        for handler_name in (
            'onFieldChange',
            'initTable',
            'addTableColumn',
            'removeTableColumn',
            'removeTableColumnAt',
            'updateColumnLabel',
            'addTableRow',
            'removeTableRow',
            'removeThisRow',
            'bindAssistPanel',
            'setAssistTab',
            'renderLivePreview',
            'triggerCalc',
        ):
            self.assertIn(handler_name, exports_block)

    def test_table_required_state_uses_non_empty_rows(self):
        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js')
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('function tableFieldHasContent', script)
        self.assertIn('return getTableRows(id).some(rowHasContent);', script)
        self.assertNotIn("const tableFilled = !!(tbody && tbody.querySelectorAll('tr').length > 0);", script)
        self.assertNotIn("if (!tbody || tbody.querySelectorAll('tr').length === 0)", script)

    def test_live_preview_renders_contract_document_blocks(self):
        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js')
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn('contract-preview-block', script)
        self.assertIn('contract-preview-line', script)
        self.assertIn('contract-preview-table', script)
        self.assertIn('function renderDocumentPreview', script)
        self.assertIn('function renderDocumentTableRow', script)
        self.assertIn('function tableColgroup', script)
        self.assertIn('function fitContractPreviewPage', script)
        self.assertIn('livePreviewSummary', script)

    def test_draft_autosave_uses_form_events_and_table_hooks(self):
        editor_script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js')
        editor_template_path = os.path.join(app.RESOURCE_DIR, 'templates', 'editor.html')
        with open(editor_script_path, 'r', encoding='utf-8') as f:
            script = f.read()
        with open(editor_template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        self.assertNotIn('_origOnFieldChange', template)
        self.assertIn("form.addEventListener('input', scheduleDraftSave);", template)
        self.assertIn("form.addEventListener('change', scheduleDraftSave);", template)
        self.assertIn("window.addEventListener('beforeunload'", template)
        self.assertIn('window.CT_scheduleDraftSave = scheduleDraftSave;', template)
        self.assertGreaterEqual(script.count('window.CT_scheduleDraftSave()'), 2)


if __name__ == '__main__':
    unittest.main()
