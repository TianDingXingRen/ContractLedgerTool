import os
import shutil
import subprocess
import unittest

import app
import field_eval


class EditorJavaScriptTests(unittest.TestCase):
    def test_editor_script_has_valid_syntax(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')

        for filename in (
            'editor.js',
            'editor-draft.js',
            'editor-bootstrap.js',
            'formula-engine.js',
            'excel-bill.js',
            'coverage-mode.js',
        ):
            script_path = os.path.join(
                app.RESOURCE_DIR, 'static', 'js', filename
            )
            with open(script_path, 'r', encoding='utf-8') as f:
                script = f.read()
            result = subprocess.run(
                [node, '--check', '-'],
                input=script,
                text=True,
                encoding='utf-8',
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                f'{filename}: {result.stderr or result.stdout}',
            )

    def test_coverage_mode_controller_updates_range_and_locked_states(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')

        script_path = os.path.join(
            app.RESOURCE_DIR, 'static', 'js', 'coverage-mode.js'
        )
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
        harness = r"""
const assert = require('node:assert/strict');
function field(value) {
  return {
    value: value || '', disabled: false, required: false, style: {},
    attributes: {}, setAttribute(name, next) { this.attributes[name] = next; }
  };
}
function fixture(mode, lockedMode) {
  const radios = [field('range'), field('not_applicable')];
  radios.forEach((radio) => { radio.checked = radio.value === mode; });
  const bounds = [field('11'), field('14')];
  const project = field('试验项目');
  const hint = field('');
  hint.textContent = '';
  const rangeFields = field('');
  const form = { querySelector() { return project; } };
  const root = {
    dataset: { coverageLocked: lockedMode || '' },
    querySelector(selector) {
      if (selector === 'input[name="coverage_mode"]:checked') {
        return radios.find((radio) => radio.checked) || null;
      }
      if (selector === '[data-coverage-hint]') return hint;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === 'input[name="coverage_mode"]') return radios;
      if (selector === '[data-coverage-bound]') return bounds;
      if (selector === '[data-coverage-range-fields]') return [rangeFields];
      return [];
    },
    closest() { return form; }
  };
  return { root, radios, bounds, project, hint, rangeFields };
}
const notApplicable = fixture('not_applicable');
window.CoverageMode.sync(notApplicable.root);
assert.equal(notApplicable.bounds[0].disabled, true);
assert.equal(notApplicable.bounds[0].value, '11');
assert.equal(notApplicable.project.required, false);
assert.match(notApplicable.hint.textContent, /不按发次归集/);

const range = fixture('range', 'range');
window.CoverageMode.sync(range.root);
assert.equal(range.bounds[0].required, true);
assert.equal(range.project.required, true);
assert.equal(range.radios[1].disabled, true);
assert.match(range.hint.textContent, /已锁定/);
"""
        result = subprocess.run(
            [node, '-'],
            input=(
                "global.window = {};\n"
                "global.document = {readyState: 'complete', "
                "querySelectorAll() { return []; }};\n"
                + script
                + harness
            ),
            text=True,
            encoding='utf-8',
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_contract_forms_expose_explicit_coverage_modes(self):
        template_dir = os.path.join(app.RESOURCE_DIR, 'templates')
        for filename in ('editor.html', 'contract_import_review.html'):
            with open(
                os.path.join(template_dir, filename), encoding='utf-8'
            ) as f:
                template = f.read()
            self.assertIn('name="coverage_mode"', template)
            self.assertIn('value="range" required', template)
            self.assertIn('value="not_applicable" required', template)
            self.assertIn("static_url('js/coverage-mode.js')", template)

        with open(
            os.path.join(template_dir, 'contract_detail.html'), encoding='utf-8'
        ) as f:
            detail = f.read()
        self.assertIn('data-coverage-locked="{{ coverage_mode }}"', detail)
        self.assertIn("coverage_mode == 'not_applicable'", detail)
        self.assertIn('所属发次不适用', detail)

        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor-draft.js'),
            encoding='utf-8',
        ) as f:
            draft = f.read()
        self.assertIn('data._coverage_mode', draft)
        self.assertIn('window.CoverageMode.syncAll(document)', draft)

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

    def test_invoice_and_excel_bill_async_loaders_guard_latest_selection(self):
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'invoice-form.js'),
            encoding='utf-8',
        ) as f:
            invoice_form = f.read()
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'excel-bill.js'),
            encoding='utf-8',
        ) as f:
            excel_bill = f.read()

        self.assertIn('new AbortController()', invoice_form)
        self.assertIn('targetRequests.get(row) !== controller', invoice_form)
        self.assertIn('contractField.value !== contract', invoice_form)
        self.assertIn('if (!response.ok)', invoice_form)
        self.assertIn('const previousNoticeId = noticeField.value;', invoice_form)
        self.assertIn('const previousPlanId = planField.value;', invoice_form)
        self.assertRegex(
            invoice_form,
            r"data\.notices \|\| \[\],\s*'不关联',\s*contract,\s*previousNoticeId",
        )
        self.assertRegex(
            invoice_form,
            r"data\.plans \|\| \[\],\s*'不关联',\s*contract,\s*previousPlanId",
        )
        self.assertIn('MAX_ALLOCATION_ROWS = 100', invoice_form)
        self.assertIn("currencyField.value = 'CNY'", invoice_form)
        self.assertIn('currencyField.readOnly = true', invoice_form)
        self.assertIn('pendingTargetLoads += 1;', invoice_form)
        self.assertIn('pendingTargetLoads - 1', invoice_form)
        self.assertIn("invoiceForm.addEventListener('submit'", invoice_form)
        self.assertIn('event.preventDefault();', invoice_form)
        self.assertIn('button.disabled = true;', invoice_form)
        self.assertNotIn(
            "replaceOptions(noticeField, [], '加载中…'",
            invoice_form,
        )

        self.assertIn('new AbortController()', excel_bill)
        self.assertIn('requestId !== contractItemsRequestId', excel_bill)
        self.assertIn('contractSelect.value !== cid', excel_bill)
        self.assertIn('if (!resp.ok)', excel_bill)
        loading = excel_bill.index("textContent = '加载中…';")
        request = excel_bill.index('    try {', loading)
        self.assertIn('updateMappingUI();', excel_bill[loading:request])

    def test_formula_engine_propagates_chains_and_uses_half_up_rounding(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'formula-engine.js'),
            encoding='utf-8',
        ) as f:
            formula_engine = f.read()

        harness = r"""
const assert = require('node:assert/strict');
const calcB = {id: 'calc_2', value: '', placeholder: '', dataset: {formula: 'a', decimals: '2'}};
const calcC = {id: 'calc_3', value: '', placeholder: '', dataset: {formula: 'b * 2', decimals: '2'}};
const hiddenB = {value: ''};
const hiddenC = {value: ''};
const sourceInput = {value: '1.005'};
const fieldItems = {
  field_1: {querySelector() { return sourceInput; }},
  field_2: {querySelector() { return calcB; }},
  field_3: {querySelector() { return calcC; }},
};
global.window = {
  ContractEditor: {config: {fields: [
    {id: 1, key: 'a', field_type: 'number'},
    {id: 2, key: 'b', field_type: 'calculated', depends_on: ['a']},
    {id: 3, key: 'c', field_type: 'calculated', depends_on: ['b']},
  ]}},
};
global.document = {
  getElementById(id) {
    if (id === 'calc_input_2') return hiddenB;
    if (id === 'calc_input_3') return hiddenC;
    return fieldItems[id] || null;
  },
  // Deliberately reverse DOM order to verify dependency sorting.
  querySelectorAll(selector) { return selector === '.calc-result' ? [calcC, calcB] : []; },
};
""" + formula_engine + r"""
const engine = window.ContractFormulaEngine;
assert.equal(engine.formatNumber(1.005, 2), '1.01');
assert.equal(engine.formatNumber(-1.005, 2), '-1.01');
assert.equal(engine.formatNumber(engine.safeEval('0.1 + 0.2', {}), 2), '0.30');
assert.equal(engine.safeEval('SUM(a * 2, b + 1)', {a: 2, b: 3}), 8);
assert.equal(engine.safeEval('+1e2', {}), 100);
assert.equal(engine.safeEval('amount + rate', {amount: '1,234.50', rate: '12%'}), 1234.62);
assert.equal(engine.safeEval('SUM(lines, qty)', {
  lines: {__tableRows: [{qty: '1,000'}], __tableColumns: ['qty']},
}), 0);
assert.throws(() => engine.formatNumber(1000000000000, 3), /精确预览范围/);
engine.triggerCalc(1);
assert.equal(calcB.value, '1.01');
assert.equal(calcC.value, '2.02');
assert.equal(hiddenC.value, '2.02');
const table = engine.calculateTableRow([
  {key: 'subtotal', field_type: 'calculated', formula: 'price', decimal_places: 2},
  {key: 'total', field_type: 'calculated', formula: 'subtotal * 2', decimal_places: 2},
], {price: 1.005});
assert.deepEqual(table, {subtotal: '1.01', total: '2.02'});
assert.deepEqual(engine.calculateTableRow([
  {key: 'total', field_type: 'calculated', formula: 'price * rate', decimal_places: 2},
], {price: '1,000.25', rate: '12%'}), {total: '120.03'});
"""
        result = subprocess.run(
            [node, '-'], input=harness, text=True, encoding='utf-8',
            capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(
            field_eval.format_number_text(
                field_eval.safe_eval_decimal('+1e2'), 2
            ),
            '100.00',
        )
        self.assertEqual(
            field_eval.format_number_text(
                field_eval.safe_eval_decimal(
                    'amount + rate', {'amount': 1234.5, 'rate': 0.12}
                ),
                2,
            ),
            '1234.62',
        )

    def test_editor_guards_generation_paste_progress_and_native_tab(self):
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor.js'),
            encoding='utf-8',
        ) as f:
            editor = f.read()

        self.assertIn('if (generationInFlight) return;', editor)
        self.assertIn('button[type="submit"], input[type="submit"]', editor)
        self.assertIn('const colIdx = editableCols[dc];', editor)
        self.assertNotIn(
            "if (columns[colIdx].field_type === 'calculated') continue;", editor
        )
        self.assertNotIn("if (e.key !== 'Tab') return;", editor)
        self.assertIn('let fillableTotal = 0;', editor)
        self.assertIn('(filled / fillableTotal) * 100', editor)
        self.assertIn('window.ContractEditor.draft.preserve();', editor)

    def test_editor_initialization_and_drafts_are_schema_guarded(self):
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor-bootstrap.js'),
            encoding='utf-8',
        ) as f:
            bootstrap = f.read()
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor-draft.js'),
            encoding='utf-8',
        ) as f:
            draft = f.read()

        self.assertLess(bootstrap.index('draftRestoring = true;'), bootstrap.index('initTable(field.id);'))
        self.assertIn('finally {', bootstrap)
        self.assertIn("var draftKey = 'ct_draft_v3_'", draft)
        self.assertIn('data._template_schema = draftTemplateSchema;', draft)
        self.assertIn('data._template_schema !== draftTemplateSchema', draft)
        self.assertIn('data._template_revision = draftTemplateRevision;', draft)
        self.assertIn('data._draft_scope = draftScope;', draft)
        self.assertIn('data._template_revision !== draftTemplateRevision', draft)
        self.assertIn('data._draft_scope !== draftScope', draft)
        self.assertIn('function parseDraftTables(data)', draft)

    def test_editor_bootstrap_keeps_table_initialization_clean(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'editor-bootstrap.js'),
            encoding='utf-8',
        ) as f:
            bootstrap = f.read()
        harness = r"""
const assert = require('node:assert/strict');
let ready;
let dirty = false;
global.draftRestoring = false;
global.fields = [{id: 9, field_type: 'table'}];
global.initTable = function() { if (!draftRestoring) dirty = true; };
global.recalcAllFields = function() {};
global.updateProgress = function() {};
global.bindEditorFilters = function() {};
global.bindAssistPanel = function() {};
global.setEditorFilter = function() {};
global.restoreDraft = function() { if (!draftRestoring) dirty = true; };
global.bindDraftAutoSave = function() {};
global.document = {
  addEventListener(event, callback) { if (event === 'DOMContentLoaded') ready = callback; },
  getElementById() { return null; },
};
""" + bootstrap + r"""
ready();
assert.equal(dirty, false);
assert.equal(draftRestoring, false);
"""
        result = subprocess.run(
            [node, '-'], input=harness, text=True, encoding='utf-8',
            capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_excel_bill_latest_preset_and_immediate_mapping_behavior(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        with open(
            os.path.join(app.RESOURCE_DIR, 'static', 'js', 'excel-bill.js'),
            encoding='utf-8',
        ) as f:
            excel_bill = f.read()
        harness = r"""
const assert = require('node:assert/strict');
const pending = {};
const elements = {
  billForm: {addEventListener() {}},
  presetKey: {value: 'old'},
  headerFields: {innerHTML: ''},
  mappingRows: {innerHTML: ''},
  contractSelect: {value: ''},
};
const mappingSelect = {value: '', options: [{value: ''}, {value: 'source'}]};
global.window = {
  ContractToolApi: {
    request() { throw new Error('unexpected request'); },
    escapeHtml(value) { return String(value == null ? '' : value); },
  },
};
global.document = {
  addEventListener() {},
  getElementById(id) { return elements[id] || null; },
  querySelector(selector) {
    return selector === '[name="map_target"]' ? mappingSelect : null;
  },
  querySelectorAll() { return []; },
};
global.showToast = function() {};
global.fetch = function(url) {
  return new Promise(resolve => { pending[url] = resolve; });
};
""" + excel_bill + r"""
function response(payload) {
  return {ok: true, status: 200, json: async function() { return payload; }};
}
(async function() {
  const oldLoad = loadPreset('old');
  elements.presetKey.value = 'new';
  const newLoad = loadPreset('new');
  pending['/api/excel-bill/presets/new'](response({
    key: 'new', header_columns: [{key: 'new_field', label: 'New'}], detail_columns: [],
  }));
  assert.equal(await newLoad, true);
  pending['/api/excel-bill/presets/old'](response({
    key: 'old', header_columns: [{key: 'old_field', label: 'Old'}], detail_columns: [],
  }));
  assert.equal(await oldLoad, false);
  assert.equal(currentPreset.key, 'new');
  assert.match(elements.headerFields.innerHTML, /new_field/);
  fillDefaultsData({name: 'saved', column_mapping: {target: 'source'}});
  assert.equal(mappingSelect.value, 'source');
  assert.equal(window._pendingMapping, null);
})().catch(function(error) { console.error(error); process.exitCode = 1; });
"""
        result = subprocess.run(
            [node, '-'], input=harness, text=True, encoding='utf-8',
            capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == '__main__':
    unittest.main()
