    let fieldCount = 0;

    function v(val) { return (val != null && val !== '') ? String(val) : ''; }

    function setFieldValue(root, name, value) {
        const control = root.querySelector(`[name="${name}"]`);
        if (control) control.value = v(value);
    }

    function addField(data) {
        data = data || {};
        const idx = fieldCount++;
        const container = document.getElementById('fieldsContainer');

        const div = document.createElement('div');
        div.className = 'builder-field-item card bg-base-200/50 border border-base-300 rounded-lg p-5 transition-all';
        div.dataset.fieldIndex = idx;
        div.innerHTML = `
            <div class="builder-field-header flex items-center gap-3 mb-3">
                <span class="field-type-badge type-text badge badge-sm" id="badge_${idx}">文本</span>
                <span class="field-index w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-semibold flex items-center justify-center">${idx + 1}</span>
                <input type="text" name="field_label_${idx}" value=""
                       class="config-input label-input input input-bordered input-sm flex-1"
                       placeholder="字段名称，如：甲方名称" data-builder-action="update-label" data-field-index="${idx}">
            </div>
            <div class="builder-field-config">
                <input type="hidden" name="field_key_${idx}" value="">
                <input type="hidden" name="field_body_index_${idx}" value="">
                <input type="hidden" name="field_placeholder_${idx}" value="">
                <input type="hidden" name="field_table_index_${idx}" value="">
                <input type="hidden" name="field_row_index_${idx}" value="">
                <input type="hidden" name="field_col_index_${idx}" value="">
                <input type="hidden" name="field_template_row_index_${idx}" value="">
                <div class="field-location-hint text-xs text-info bg-info/10 rounded px-3 py-1.5 mb-3" style="display:none">&#128206; 已关联样式位置</div>
                <div class="variable-hint text-xs text-base-content/50 mb-3">
                    公式变量名：<code id="field_var_${idx}" class="badge badge-neutral badge-sm font-mono"></code>
                </div>
                <div class="config-row flex items-center gap-3 mb-3">
                    <label class="text-xs text-base-content/60 w-12">类型：</label>
                    <select name="field_type_${idx}" class="config-input field-type-select select select-bordered select-xs"
                            data-builder-action="field-type" data-field-index="${idx}">
                        <option value="text">文本 (单行)</option>
                        <option value="number">数字</option>
                        <option value="textarea">段落 (多行)</option>
                        <option value="select">下拉选择</option>
                        <option value="table">表格</option>
                        <option value="calculated">自动计算</option>
                    </select>
                </div>
                <div class="config-row mb-3">
                    <label class="checkbox-wrap-inline inline-flex items-center gap-2 text-sm cursor-pointer">
                        <input type="checkbox" name="field_required_${idx}" class="checkbox checkbox-xs"> 必填
                    </label>
                </div>

                <div class="type-config type-config-default" id="config_default_${idx}">
                    <div class="config-row flex items-start gap-3 mb-3">
                        <label class="text-xs text-base-content/60 w-12 pt-1">预制内容：</label>
                        <textarea name="field_default_${idx}" class="config-input options-input textarea textarea-bordered textarea-xs flex-1"
                                  rows="2" placeholder="打开填写页时自动带出的标准内容"></textarea>
                    </div>
                </div>

                <div class="type-config type-config-select" id="config_select_${idx}" style="display:none">
                    <div class="config-row flex items-start gap-3 mb-3">
                        <label class="text-xs text-base-content/60 w-12 pt-1">选项：</label>
                        <textarea name="field_options_${idx}" class="config-input options-input textarea textarea-bordered textarea-xs flex-1"
                                  rows="3" placeholder="每行一个选项"></textarea>
                    </div>
                </div>

                <div class="type-config type-config-number" id="config_number_${idx}" style="display:none">
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                        <label class="form-control">
                            <span class="label-text text-xs text-base-content/60 mb-1">最小值</span>
                            <input type="number" step="any" name="field_number_min_${idx}" value=""
                                   class="input input-bordered input-sm" placeholder="可选">
                        </label>
                        <label class="form-control">
                            <span class="label-text text-xs text-base-content/60 mb-1">最大值</span>
                            <input type="number" step="any" name="field_number_max_${idx}" value=""
                                   class="input input-bordered input-sm" placeholder="可选">
                        </label>
                        <label class="form-control">
                            <span class="label-text text-xs text-base-content/60 mb-1">小数位</span>
                            <select name="field_number_decimal_${idx}" class="select select-bordered select-sm">
                                <option value="0">0</option><option value="1">1</option>
                                <option value="2" selected>2</option><option value="3">3</option>
                                <option value="4">4</option><option value="5">5</option><option value="6">6</option>
                            </select>
                        </label>
                    </div>
                </div>

                <div class="type-config type-config-calculated" id="config_calculated_${idx}" style="display:none">
                    <div class="config-row flex items-center gap-3 mb-3">
                        <label class="text-xs text-base-content/60 w-12">公式：</label>
                        <input type="text" name="field_formula_${idx}" value=""
                               class="config-input formula-input input input-bordered input-sm flex-1 max-w-sm font-mono"
                               placeholder="例如: qty * unit_price">
                    </div>
                    <div class="config-row flex items-center gap-3 mb-3">
                        <label class="text-xs text-base-content/60 w-12">小数位：</label>
                        <select name="field_decimal_${idx}" class="config-input select select-bordered select-xs">
                            <option value="0">0</option><option value="1">1</option>
                            <option value="2" selected>2</option><option value="4">4</option>
                        </select>
                    </div>
                </div>

                <div class="type-config type-config-table" id="config_table_${idx}" style="display:none">
                    <div class="text-xs text-base-content/60 mb-2">列定义：</div>
                    <div class="table-columns-editor bg-base-200 rounded-lg p-3 mb-3" id="col_editor_${idx}"></div>
                    <button type="button" class="btn btn-ghost btn-xs" data-builder-action="add-column" data-field-index="${idx}">
                        <i data-lucide="plus" class="w-3 h-3"></i> 添加列
                    </button>
                </div>

                <div class="config-row mt-4 pt-3 border-t border-base-300">
                    <button type="button" class="btn btn-error btn-xs btn-outline btn-sm btn-danger"
                            data-builder-action="remove-field">删除此字段</button>
                </div>
            </div>
        `;
        container.appendChild(div);
        setFieldValue(div, `field_label_${idx}`, data.label);
        setFieldValue(div, `field_key_${idx}`, data.key);
        setFieldValue(div, `field_body_index_${idx}`, data.body_index);
        setFieldValue(div, `field_placeholder_${idx}`, data.placeholder);
        setFieldValue(div, `field_table_index_${idx}`, data.table_index);
        setFieldValue(div, `field_row_index_${idx}`, data.row_index);
        setFieldValue(div, `field_col_index_${idx}`, data.col_index);
        setFieldValue(div, `field_template_row_index_${idx}`, data.template_row_index);
        setFieldValue(div, `field_default_${idx}`, data.default_value);
        setFieldValue(
            div,
            `field_options_${idx}`,
            Array.isArray(data.options) ? data.options.join('\n') : '选项1\n选项2\n选项3'
        );
        setFieldValue(div, `field_number_min_${idx}`, data.min_value);
        setFieldValue(div, `field_number_max_${idx}`, data.max_value);
        setFieldValue(div, `field_formula_${idx}`, data.formula);

        const fieldTypes = new Set(['text', 'number', 'textarea', 'select', 'table', 'calculated']);
        const fieldType = fieldTypes.has(data.field_type) ? data.field_type : 'text';
        div.querySelector('.field-type-select').value = fieldType;
        div.querySelector(`[name="field_required_${idx}"]`).checked = Boolean(data.required);
        const decimalPlaces = Number.isInteger(Number(data.decimal_places))
            ? Math.min(6, Math.max(0, Number(data.decimal_places)))
            : 2;
        div.querySelector(`[name="field_number_decimal_${idx}"]`).value = String(decimalPlaces);
        const calculatedDecimal = [0, 1, 2, 4].includes(decimalPlaces) ? decimalPlaces : 2;
        div.querySelector(`[name="field_decimal_${idx}"]`).value = String(calculatedDecimal);
        const locationHint = div.querySelector('.field-location-hint');
        if (data.body_index != null || data.table_index != null || data.template_row_index != null) {
            locationHint.style.display = 'inline-block';
        }

        const columns = Array.isArray(data.columns) && data.columns.length > 0 ? data.columns : [
            {label:'产品名称', field_type:'text'},
            {label:'数量', field_type:'text'},
            {label:'单价', field_type:'text'},
            {label:'小计', field_type:'calculated', formula:'qty * unit_price'}
        ];
        columns.forEach(column => addColumn(idx, column));
        div.scrollIntoView({behavior: 'smooth', block: 'center'});
        updateLabel(div.querySelector('.label-input'), idx);
        if (data.key) {
            const varEl = document.getElementById('field_var_' + idx);
            if (varEl) varEl.textContent = data.key;
            const hidden = document.querySelector(`[name="field_key_${idx}"]`);
            if (hidden) hidden.value = data.key;
        }
        bindColumnLabelHints(div);
        onTypeChange(div.querySelector('.field-type-select'), idx);
        // icons auto-rendered by icons.js
    }

    function updateLabel(input, idx) {
        const badge = document.getElementById('badge_' + idx);
        if (badge) {
            const val = input.value.trim();
            badge.textContent = val || '新字段';
        }
        const varEl = document.getElementById('field_var_' + idx);
        if (varEl) {
            const key = makeFieldKey(input.value, 'field_' + idx);
            varEl.textContent = key;
            const hidden = document.querySelector(`[name="field_key_${idx}"]`);
            if (hidden) hidden.value = key;
        }
    }

    function onTypeChange(select, idx) {
        const badge = document.getElementById('badge_' + idx);
        const typeNames = {text:'文本', number:'数字', textarea:'段落', select:'选择', table:'表格', calculated:'计算'};
        const typeColors = {text:'badge-primary', number:'badge-accent', textarea:'badge-secondary', select:'badge-info', table:'badge-success', calculated:'badge-warning'};
        badge.textContent = typeNames[select.value] || select.value;
        badge.className = 'field-type-badge badge badge-sm ' + (typeColors[select.value] || 'badge-primary');
        ['number', 'select', 'calculated', 'table'].forEach(t => {
            const el = document.getElementById('config_' + t + '_' + idx);
            if (el) el.style.display = (t === select.value) ? 'block' : 'none';
        });
        const defaultBox = document.getElementById('config_default_' + idx);
        if (defaultBox) {
            defaultBox.style.display = ['table', 'calculated'].includes(select.value) ? 'none' : 'block';
        }
    }

    function removeField(btn) {
        const item = btn.closest('.builder-field-item');
        if (document.querySelectorAll('.builder-field-item').length <= 1) {
            showToast('至少保留一个字段', 'error');
            return;
        }
        item.remove();
        renumberFields();
    }

    function renumberFields() {
        document.querySelectorAll('.builder-field-item').forEach((item, i) => {
            const span = item.querySelector('.field-index');
            if (span) span.textContent = i + 1;
        });
    }

    function addColumn(fieldIdx, columnData) {
        columnData = columnData || {};
        const editor = document.getElementById('col_editor_' + fieldIdx);
        if (!editor) return;
        const rows = editor.querySelectorAll('.column-row');
        const ci = rows.length;
        const row = document.createElement('div');
        row.className = 'column-row bg-base-100 border border-base-300 rounded-lg p-3 mb-2';
        row.innerHTML = `
            <div class="flex items-center justify-between gap-2 mb-2">
                <div class="text-xs font-semibold text-base-content/60"></div>
                <button type="button" class="btn btn-ghost btn-xs text-error" data-builder-action="remove-column" title="删除此列">
                    <i data-lucide="x" class="w-3 h-3"></i>
                </button>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-[minmax(150px,1.1fr)_120px_minmax(180px,1fr)] gap-2 items-end">
                <label class="form-control">
                    <span class="label-text text-xs text-base-content/50 mb-1">列名</span>
                    <input type="text" value="" class="col-input input input-bordered input-sm w-full" placeholder="如：产品名称">
                </label>
                <label class="form-control">
                    <span class="label-text text-xs text-base-content/50 mb-1">类型</span>
                    <select class="col-type-select select select-bordered select-sm w-full" data-builder-action="column-type">
                        <option value="text" selected>文本</option><option value="textarea">段落</option>
                        <option value="number">数字</option><option value="select">选择</option><option value="calculated">自动计算</option>
                    </select>
                </label>
                <label class="form-control col-default-wrap">
                    <span class="label-text text-xs text-base-content/50 mb-1">预制内容</span>
                    <input type="text" value="" class="col-input col-default-input input input-bordered input-sm w-full" placeholder="可选">
                </label>
                <label class="form-control col-formula-wrap md:col-span-3" style="display:none">
                    <span class="label-text text-xs text-base-content/50 mb-1">计算公式</span>
                    <input type="text" value="" class="col-formula-input input input-bordered input-sm w-full font-mono" placeholder="例如：qty * unit_price">
                </label>
                <label class="form-control col-options-wrap md:col-span-3" style="display:none">
                    <span class="label-text text-xs text-base-content/50 mb-1">选择项（每行一个）</span>
                    <textarea class="col-options-input textarea textarea-bordered textarea-sm" rows="2"></textarea>
                </label>
                <label class="form-control col-decimal-wrap" style="display:none">
                    <span class="label-text text-xs text-base-content/50 mb-1">小数位</span>
                    <select class="col-decimal-input select select-bordered select-sm"><option>0</option><option>1</option><option selected>2</option><option>3</option><option>4</option><option>5</option><option>6</option></select>
                </label>
            </div>
            <div class="column-var-hint text-xs text-base-content/40 mt-2">
                变量 <code class="badge badge-xs font-mono"></code>
            </div>
        `;
        editor.appendChild(row);
        const labelInput = row.querySelector('.col-input:not(.col-default-input)');
        const typeSelect = row.querySelector('.col-type-select');
        const defaultInput = row.querySelector('.col-default-input');
        const formulaInput = row.querySelector('.col-formula-input');
        const optionsInput = row.querySelector('.col-options-input');
        const decimalInput = row.querySelector('.col-decimal-input');
        labelInput.name = `col_label_${fieldIdx}_${ci}`;
        typeSelect.name = `col_type_${fieldIdx}_${ci}`;
        defaultInput.name = `col_default_${fieldIdx}_${ci}`;
        formulaInput.name = `col_formula_${fieldIdx}_${ci}`;
        optionsInput.name = `col_options_${fieldIdx}_${ci}`;
        decimalInput.name = `col_decimal_${fieldIdx}_${ci}`;
        labelInput.value = v(columnData.label);
        defaultInput.value = v(columnData.default_value);
        formulaInput.value = v(columnData.formula);
        optionsInput.value = Array.isArray(columnData.options) ? columnData.options.join('\n') : '';
        const columnTypes = new Set(['text', 'number', 'textarea', 'select', 'calculated']);
        typeSelect.value = columnTypes.has(columnData.field_type) ? columnData.field_type : 'text';
        const decimalPlaces = Number.isInteger(Number(columnData.decimal_places))
            ? Math.min(6, Math.max(0, Number(columnData.decimal_places)))
            : 2;
        decimalInput.value = String(decimalPlaces);
        row.querySelector('.text-xs.font-semibold').textContent = `第 ${ci + 1} 列`;
        row.querySelector('.column-var-hint code').textContent =
            v(columnData.key) || makeColumnKey(columnData.label, ci);
        onColTypeChange(typeSelect);
        bindColumnLabelHints(editor);
        refreshColumnRemoveButtons(editor);
        // icons auto-rendered by icons.js
    }

    function removeColumn(btn) {
        const row = btn.closest('.column-row');
        if (row && row.parentElement.querySelectorAll('.column-row').length > 1) {
            const editor = row.parentElement;
            row.remove();
            bindColumnLabelHints(editor);
            refreshColumnRemoveButtons(editor);
        }
    }

    function onColTypeChange(select) {
        const row = select.closest('.column-row');
        const formulaWrap = row ? row.querySelector('.col-formula-wrap') : null;
        const defaultWrap = row ? row.querySelector('.col-default-wrap') : null;
        const optionsWrap = row ? row.querySelector('.col-options-wrap') : null;
        const decimalWrap = row ? row.querySelector('.col-decimal-wrap') : null;
        const isCalculated = select.value === 'calculated';
        if (formulaWrap) formulaWrap.style.display = isCalculated ? 'block' : 'none';
        if (defaultWrap) defaultWrap.style.display = isCalculated ? 'none' : 'block';
        if (optionsWrap) optionsWrap.style.display = select.value === 'select' ? 'block' : 'none';
        if (decimalWrap) decimalWrap.style.display = select.value === 'number' ? 'block' : 'none';
    }

    function makeFieldKey(label, fallback) {
        let key = (label || '').replace(/[^\w一-鿿]/g, '_');
        key = key.replace(/_+/g, '_').replace(/^_+|_+$/g, '');
        return key || fallback;
    }

    function makeColumnKey(label, index) {
        const keyMap = [
            ['产品名称', 'product_name'], ['产品', 'product_name'],
            ['数量', 'qty'], ['单价', 'unit_price'], ['价格', 'unit_price'],
            ['小计', 'subtotal'], ['合计', 'subtotal'], ['金额', 'amount'],
            ['总价', 'total_price'], ['规格型号', 'spec'], ['型号', 'spec'],
            ['单位', 'uom'], ['计量单位', 'uom'], ['备注', 'remark'],
            ['说明', 'note'], ['税率', 'tax_rate'], ['税额', 'tax_amount']
        ];
        const text = label || '';
        for (const pair of keyMap) {
            if (text.indexOf(pair[0]) !== -1) return pair[1];
        }
        const cleaned = text.replace(/[^\w]/g, '').slice(0, 15);
        return cleaned || ('col_' + index);
    }

    function bindColumnLabelHints(root) {
        root.querySelectorAll('.column-row').forEach((row, ci) => {
            const input = row.querySelector('[name^="col_label_"]');
            const hint = row.querySelector('.column-var-hint code');
            if (!input || !hint) return;
            const update = () => { hint.textContent = makeColumnKey(input.value, ci); };
            input.oninput = update;
            update();
        });
    }

    function refreshColumnRemoveButtons(root) {
        const rows = root.querySelectorAll('.column-row');
        rows.forEach((row, ci) => {
            const title = row.querySelector('.text-xs.font-semibold');
            if (title) title.textContent = '第 ' + (ci + 1) + ' 列';
            const btn = row.querySelector('[data-builder-action="remove-column"]');
            if (btn) btn.style.visibility = rows.length > 1 ? 'visible' : 'hidden';
        });
    }

    // ── Form submission ──
    document.getElementById('templateForm').addEventListener('submit', function(e) {
        normalizeTemplateFormNames();
        const name = document.getElementById('template_name').value.trim();
        if (!name) {
            e.preventDefault();
            showToast('请输入模板名称', 'error');
            return;
        }
        const fields = document.querySelectorAll('.builder-field-item');
        if (fields.length === 0) {
            e.preventDefault();
            showToast('请至少添加一个字段', 'error');
            return;
        }
        document.getElementById('loadingOverlay').classList.add('active');
    });

    function renameByPrefix(root, prefix, newName) {
        const el = root.querySelector(`[name^="${prefix}"]`);
        if (el) el.name = newName;
    }

    function normalizeTemplateFormNames() {
        document.querySelectorAll('.builder-field-item').forEach((item, idx) => {
            item.dataset.fieldIndex = idx;
            const prefixes = ['field_label_','field_key_','field_body_index_','field_placeholder_',
                'field_table_index_','field_row_index_','field_col_index_','field_template_row_index_',
                'field_type_','field_required_','field_options_','field_formula_','field_decimal_','field_default_',
                'field_number_min_','field_number_max_','field_number_decimal_'];
            prefixes.forEach(p => renameByPrefix(item, p, p + idx));
            item.querySelectorAll('.column-row').forEach((row, ci) => {
                ['col_label_','col_type_','col_formula_','col_default_','col_options_','col_decimal_'].forEach(p =>
                    renameByPrefix(row, p, p + idx + '_' + ci));
            });
        });
    }

    // ── File upload ──
    function onUploadSubmit() {
        const input = document.getElementById('fileInput');
        if (!input.files || input.files.length === 0) { input.click(); return false; }
        document.getElementById('uploadStatus').style.display = 'block';
        return true;
    }
    function onFileSelected(input) {
        if (input.files && input.files.length > 0) {
            document.getElementById('uploadStatus').style.display = 'block';
            document.getElementById('uploadForm').submit();
        }
    }

    // ── Drag & drop ──
    (function() {
        const zone = document.getElementById('dropZone');
        if (zone) {
            zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
            zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
            zone.addEventListener('drop', e => {
                e.preventDefault();
                zone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    document.getElementById('uploadStatus').style.display = 'block';
                    document.getElementById('fileInput').files = files;
                    document.getElementById('uploadForm').submit();
                }
            });
        }
    })();

    document.addEventListener('click', function(event) {
        const control = event.target.closest('[data-builder-action]');
        if (!control) return;
        const action = control.dataset.builderAction;
        if (action === 'choose-file' && event.target.closest('button, input')) return;
        if (action === 'choose-file') document.getElementById('fileInput').click();
        if (action === 'choose-reupload') document.getElementById('reUploadInput').click();
        if (action === 'add-field') addField();
        if (action === 'remove-field') removeField(control);
        if (action === 'add-column') addColumn(Number(control.dataset.fieldIndex));
        if (action === 'remove-column') removeColumn(control);
    });
    document.addEventListener('input', function(event) {
        if (event.target.dataset.builderAction === 'update-label') {
            updateLabel(event.target, Number(event.target.dataset.fieldIndex));
        }
    });
    document.addEventListener('change', function(event) {
        const action = event.target.dataset.builderAction;
        if (action === 'reupload-selected' && event.target.files.length) event.target.form.submit();
        if (action === 'file-selected') onFileSelected(event.target);
        if (action === 'field-type') onTypeChange(event.target, Number(event.target.dataset.fieldIndex));
        if (action === 'column-type') onColTypeChange(event.target);
    });
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(event) {
            if (!onUploadSubmit()) event.preventDefault();
        });
    }

    // ── Init from detected fields ──
    (function initDetectedFields() {
        const configElement = document.getElementById('templateBuilderConfig');
        const detectedFields = JSON.parse(configElement ? configElement.textContent : '[]');
        if (detectedFields && detectedFields.length > 0) {
            document.getElementById('fieldsContainer').replaceChildren();
            fieldCount = 0;
            detectedFields.forEach(function(field) {
                var location = field.location || {};
                addField({
                    label: field.label, key: field.key, field_type: field.field_type || 'text',
                    body_index: location.body_index, placeholder: location.placeholder,
                    table_index: location.table_index, template_row_index: location.template_row_index,
                    row_index: location.row_index, col_index: location.col_index,
                    options: field.options, columns: field.columns, formula: field.formula,
                    default_value: field.default_value,
                });
            });
        } else {
            addField();
        }
    })();
