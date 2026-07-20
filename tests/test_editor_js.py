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

    def test_editor_uses_delegated_event_modules(self):
        script_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor-table.js')
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()

        self.assertIn("document.addEventListener('click'", script)
        self.assertIn("document.addEventListener('change'", script)
        self.assertIn("'add-row'", script)
        self.assertIn("'remove-column-at'", script)
        with open(os.path.join(app.RESOURCE_DIR, 'templates', 'editor.html'), encoding='utf-8') as f:
            template = f.read()
        self.assertNotIn('onclick=', template)
        self.assertNotIn('onchange=', template)

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
        draft_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor-draft.js')
        editor_path = os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js')
        with open(draft_path, 'r', encoding='utf-8') as f:
            draft = f.read()
        with open(editor_path, 'r', encoding='utf-8') as f:
            editor = f.read()

        self.assertIn("form.addEventListener('input', scheduleDraftSave);", draft)
        self.assertIn("form.addEventListener('change', scheduleDraftSave);", draft)
        self.assertIn("window.addEventListener('beforeunload'", draft)
        self.assertIn("event.returnValue = '';", draft)
        self.assertIn('hasUnsavedChanges', draft)
        self.assertIn('markClean: markClean', draft)
        self.assertIn('window.ContractEditor.draft', draft)
        self.assertGreaterEqual(editor.count("typeof scheduleDraftSave === 'function'"), 2)

    def test_editor_preflight_and_tabs_are_keyboard_accessible(self):
        with open(os.path.join(app.RESOURCE_DIR, 'templates', 'editor.html'), encoding='utf-8') as f:
            template = f.read()
        with open(os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js'), encoding='utf-8') as f:
            editor = f.read()

        self.assertIn('role="progressbar"', template)
        self.assertIn('aria-labelledby="preflightTitle"', template)
        self.assertIn('id="editorStatusLive" aria-live="polite"', template)
        self.assertIn("event.key === 'ArrowRight'", editor)
        self.assertIn("event.key !== 'Escape'", editor)
        self.assertIn('announceEditorStatus', editor)


if __name__ == '__main__':
    unittest.main()
