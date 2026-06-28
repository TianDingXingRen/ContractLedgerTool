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
            'triggerCalc',
        ):
            self.assertIn(handler_name, exports_block)


if __name__ == '__main__':
    unittest.main()
