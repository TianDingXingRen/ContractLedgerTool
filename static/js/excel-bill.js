// ── 全局状态 ──
let currentPreset = null;
let currentDetailColumns = [];
let contracts = [];
let selectedContractItems = [];
let contractItemsController = null;
let contractItemsRequestId = 0;

async function apiFetch(url, options = {}) {
    const opts = { ...options };
    if (!opts.headers) opts.headers = {};
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
        opts.body = JSON.stringify(opts.body);
        opts.headers['Content-Type'] = 'application/json';
    }
    return window.ContractToolApi.request(url, opts);
}

function escapeHtml(str) {
    return window.ContractToolApi.escapeHtml(str);
}

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', () => {
    loadPreset('standard_pr');
    loadContracts();
    loadSavedDefaultsList();
});

// ── 预置选择 ──
function selectPreset(key, el) {
    document.getElementById('presetKey').value = key;
    document.querySelectorAll('#presetCards > div').forEach(c => {
        c.classList.remove('border-primary');
        c.classList.add('border-transparent');
    });
    el.classList.remove('border-transparent');
    el.classList.add('border-primary');
    loadPreset(key);
}

async function loadPreset(key) {
    try {
        const resp = await fetch('/api/excel-bill/presets/' + key);
        const preset = await resp.json();
        if (preset.error) { showToast(preset.error, 'error'); return; }
        currentPreset = preset;
        currentDetailColumns = preset.detail_columns || [];
        renderHeaderFields(preset.header_columns);
        updateMappingUI();
    } catch (e) {
        showToast('加载预设失败: ' + e.message, 'error');
    }
}

function renderHeaderFields(columns) {
    const container = document.getElementById('headerFields');
    container.innerHTML = columns.map(col => {
        const isBillNo = col.key === 'bill_no';
        const safeLabel = escapeHtml(col.label);
        return '<label class="form-control">' +
            '<span class="label-text text-xs text-base-content/60 pb-1">' + safeLabel + '</span>' +
            '<input name="h_' + escapeHtml(col.key) + '" class="input input-bordered input-sm" ' +
            'placeholder="' + safeLabel + '" ' +
            (isBillNo ? 'id="billNoInput"' : '') + '>' +
            '</label>';
    }).join('');
}

// ── 合同列表 ──
async function loadContracts() {
    try {
        const resp = await fetch('/api/excel-bill/contracts');
        const data = await resp.json();
        contracts = data.contracts || [];
        const sel = document.getElementById('contractSelect');
        contracts.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = (c.contract_no || '#' + c.id) + ' ' + c.title;
            if (!c.has_table3) opt.textContent += ' (无采购标的)';
            sel.appendChild(opt);
        });
    } catch (e) {
        showToast('加载合同列表失败', 'error');
    }
}

// ── 合同关联 ──
function toggleContractSection() {
    const content = document.getElementById('contractContent');
    const btn = document.getElementById('contractToggleText');
    content.classList.toggle('hidden');
    btn.textContent = content.classList.contains('hidden') ? '展开' : '收起';
}

async function onContractChange() {
    const contractSelect = document.getElementById('contractSelect');
    const cid = contractSelect.value;
    const requestId = ++contractItemsRequestId;
    if (contractItemsController) contractItemsController.abort();
    contractItemsController = null;
    document.getElementById('contractId').value = cid;
    document.getElementById('columnMappingSection').classList.toggle('hidden', !cid);
    document.getElementById('defaultValues').classList.toggle('hidden', !cid);
    document.getElementById('previewSection').classList.toggle('hidden', !cid);

    if (!cid) {
        selectedContractItems = [];
        document.getElementById('contractItemCount').textContent = '';
        updateMappingUI();
        renderPreview();
        return;
    }

    const controller = new AbortController();
    contractItemsController = controller;
    selectedContractItems = [];
    document.getElementById('contractItemCount').textContent = '加载中…';
    updateMappingUI();
    renderPreview();
    try {
        const resp = await fetch('/api/excel-bill/contracts/' + cid + '/items', {
            headers: { Accept: 'application/json' },
            signal: controller.signal,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.error || `请求失败（${resp.status}）`);
        }
        if (requestId !== contractItemsRequestId || contractSelect.value !== cid) return;
        selectedContractItems = data.items || [];
        document.getElementById('contractItemCount').textContent =
            '共 ' + data.item_count + ' 行采购标的';
        updateMappingUI();
        // Apply pending column mapping from loaded defaults
        if (window._pendingMapping) {
            Object.entries(window._pendingMapping).forEach(([key, val]) => {
                const sel = document.querySelector('[name=\"map_' + key + '\"]');
                if (sel && val) sel.value = val;
            });
            window._pendingMapping = null;
        }
        renderPreview();
    } catch (e) {
        if (e.name === 'AbortError') return;
        if (requestId !== contractItemsRequestId || contractSelect.value !== cid) return;
        selectedContractItems = [];
        document.getElementById('contractItemCount').textContent = '加载失败';
        updateMappingUI();
        renderPreview();
        showToast('加载采购标的数据失败: ' + e.message, 'error');
    } finally {
        if (contractItemsController === controller) contractItemsController = null;
    }
}

// ── 列映射 UI ──
function updateMappingUI() {
    const container = document.getElementById('mappingRows');
    const cid = document.getElementById('contractSelect').value;
    if (!cid || !currentDetailColumns || currentDetailColumns.length === 0) {
        container.innerHTML = '';
        return;
    }

    // 找到选中合同的列信息
    const contract = contracts.find(c => c.id == cid);
    const srcCols = contract ? (contract.table3_columns || []) : [];

    // 默认映射建议
    const defaultMapping = {
        'material_name': 'product_name',
        'material_code': 'spec',
        'total_qty': 'qty',
        'unit_price_tax': 'unit_price',
        'total_tax': 'subtotal',
        'cooperation_content': 'remark',
        'spec': 'spec',
    };

    container.innerHTML = currentDetailColumns.map(dc => {
        const srcKey = defaultMapping[dc.key] || '';
        const safeLabel = escapeHtml(dc.label);
        let options = '<option value="">-- 不映射 --</option>';
        srcCols.forEach(sc => {
            const sel = sc.key === srcKey ? ' selected' : '';
            options += '<option value="' + escapeHtml(sc.key) + '"' + sel + '>' + escapeHtml(sc.label) + '</option>';
        });
        return '<div class="flex items-center gap-2 text-sm">' +
            '<span class="w-32 text-right text-base-content/50 truncate">' + safeLabel + '</span>' +
            '<span class="text-base-content/30">←</span>' +
            '<select name="map_' + escapeHtml(dc.key) + '" class="select select-bordered select-xs flex-1 max-w-xs">' +
            options + '</select>' +
            '</div>';
    }).join('');
}

// ── 预览 ──
function renderPreview() {
    const thead = document.getElementById('previewHead');
    const tbody = document.getElementById('previewBody');
    if (selectedContractItems.length === 0) {
        thead.innerHTML = '';
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-base-content/40">无数据</td></tr>';
        return;
    }
    // 显示采购标的原始列
    const cols = Object.keys(selectedContractItems[0]);
    thead.innerHTML = '<tr>' + cols.map(c => '<th class="text-xs">' + escapeHtml(c) + '</th>').join('') + '</tr>';
    tbody.innerHTML = selectedContractItems.slice(0, 10).map(row =>
        '<tr>' + cols.map(c => '<td class="text-xs">' + escapeHtml(row[c] || '') + '</td>').join('') + '</tr>'
    ).join('');
}

// ── 表单提交前处理 ──
document.getElementById('billForm').addEventListener('submit', function(e) {
    // 收集表头数据
    const headerData = {};
    if (currentPreset && currentPreset.header_columns) {
        currentPreset.header_columns.forEach(col => {
            const input = document.querySelector('[name="h_' + col.key + '"]');
            if (input) headerData[col.key] = input.value;
        });
    }
    document.getElementById('headerData').value = JSON.stringify(headerData);

    // 收集列映射
    const cid = document.getElementById('contractSelect').value;
    if (cid && currentDetailColumns.length > 0) {
        const mapping = {};
        currentDetailColumns.forEach(dc => {
            const sel = document.querySelector('[name="map_' + dc.key + '"]');
            if (sel && sel.value) mapping[dc.key] = sel.value;
        });
        document.getElementById('columnMapping').value = JSON.stringify(mapping);
    }
});

// ── 预览数据 ──
function previewData() {
    const headerData = {};
    if (currentPreset && currentPreset.header_columns) {
        currentPreset.header_columns.forEach(col => {
            const input = document.querySelector('[name="h_' + col.key + '"]');
            if (input) headerData[col.key] = input.value || '(空)';
        });
    }
    const msg = '表头数据:\n' + JSON.stringify(headerData, null, 2) +
        '\n\n关联合同: ' + (document.getElementById('contractSelect').value || '无') +
        '\n采购标的总行数: ' + selectedContractItems.length;
    window.showNotice('预览数据', msg);
}

// ── 保存/加载表头默认值 ──

function getCurrentHeaderData() {
    const data = {};
    if (currentPreset && currentPreset.header_columns) {
        currentPreset.header_columns.forEach(col => {
            const input = document.querySelector('[name="h_' + col.key + '"]');
            if (input) data[col.key] = input.value;
        });
    }
    return data;
}

function getCurrentDetailDefaults() {
    const data = {};
    ['buyer', 'required_date', 'suggested_order_date'].forEach(k => {
        const input = document.querySelector('[name="default_' + k + '"]');
        if (input && input.value) data[k] = input.value;
    });
    return data;
}

function getCurrentMapping() {
    const mapping = {};
    if (currentDetailColumns.length > 0) {
        currentDetailColumns.forEach(dc => {
            const sel = document.querySelector('[name="map_' + dc.key + '"]');
            if (sel && sel.value) mapping[dc.key] = sel.value;
        });
    }
    return mapping;
}

function showSaveDialog() {
    document.getElementById('saveDialog').showModal();
    document.getElementById('saveName').focus();
}

async function saveDefaults() {
    const name = document.getElementById('saveName').value.trim();
    if (!name) { showToast('请输入保存名称', 'error'); return; }

    const payload = {
        preset_key: document.getElementById('presetKey').value,
        name: name,
        header_data: getCurrentHeaderData(),
        detail_defaults: getCurrentDetailDefaults(),
        column_mapping: getCurrentMapping(),
    };

    try {
        const resp = await apiFetch('/api/excel-bill/defaults', {
            method: 'POST',
            body: payload,
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast(data.message || '保存成功');
            document.getElementById('saveDialog').close();
            document.getElementById('saveName').value = '';
            loadSavedDefaultsList();
        } else {
            showToast(data.error || '保存失败', 'error');
        }
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

function appendEmptyDefaultsItem(menu) {
    const item = document.createElement('li');
    const label = document.createElement('span');
    label.className = 'text-base-content/40 text-xs px-2';
    label.textContent = '暂无保存记录';
    item.appendChild(label);
    menu.appendChild(item);
}

function appendDefaultsItem(menu, item, presetName) {
    const row = document.createElement('li');
    const link = document.createElement('a');
    link.className = 'flex justify-between items-center cursor-pointer';
    link.dataset.billAction = 'load-defaults';
    link.dataset.filename = item.filename || '';
    const name = document.createElement('span');
    name.className = 'text-sm truncate max-w-40';
    name.textContent = item.name || '';
    link.appendChild(name);
    const meta = document.createElement('span');
    meta.className = presetName ? 'badge badge-xs badge-ghost' : 'text-xs text-base-content/30';
    meta.textContent = presetName || String(item.saved_at || '').substring(0, 10);
    link.appendChild(meta);
    row.appendChild(link);
    menu.appendChild(row);
}

async function loadSavedDefaultsList() {
    const pk = document.getElementById('presetKey').value;
    try {
        const resp = await fetch('/api/excel-bill/defaults?preset_key=' + pk);
        const data = await resp.json();
        const items = data.defaults || [];
        const menu = document.getElementById('savedDefaultsMenu');
        // Clear old items
        menu.querySelectorAll('li:not(.menu-title)').forEach(li => li.remove());

        if (items.length === 0) {
            appendEmptyDefaultsItem(menu);
        } else {
            items.forEach(item => {
                appendDefaultsItem(menu, item, '');
            });
            // Add "manage" option
            const li = document.createElement('li');
            const divider = document.createElement('div');
            divider.className = 'divider my-0';
            const all = document.createElement('a');
            all.className = 'text-xs text-base-content/40';
            all.dataset.billAction = 'load-all-defaults';
            all.textContent = '显示全部预设的记录';
            li.appendChild(divider);
            li.appendChild(all);
            menu.appendChild(li);
        }
    } catch (e) {
        console.error('Load defaults list failed:', e);
    }
}

async function loadDefaults(filename) {
    try {
        const resp = await window.ContractToolApi.request('/api/excel-bill/defaults/' + encodeURIComponent(filename));
        if (!resp.ok) { showToast('加载失败', 'error'); return; }
        const record = await resp.json();

        // 如果预设不同，先切换
        if (record.preset_key && record.preset_key !== document.getElementById('presetKey').value) {
            document.getElementById('presetKey').value = record.preset_key;
            // 找到对应卡片并选中
            document.querySelectorAll('#presetCards > div').forEach(card => {
                const pkey = card.getAttribute('data-preset');
                card.classList.toggle('border-primary', pkey === record.preset_key);
                card.classList.toggle('border-transparent', pkey !== record.preset_key);
            });
            await loadPreset(record.preset_key);
            // loadPreset 已同步渲染 DOM，直接填值
            fillDefaultsData(record);
        } else {
            fillDefaultsData(record);
        }
    } catch (e) {
        showToast('加载失败: ' + e.message, 'error');
    }
}

function fillDefaultsData(record) {
    // Fill header fields
    if (record.header_data) {
        Object.entries(record.header_data).forEach(([key, val]) => {
            const input = document.querySelector('[name="h_' + key + '"]');
            if (input) input.value = val;
        });
    }
    // Fill detail defaults
    if (record.detail_defaults) {
        Object.entries(record.detail_defaults).forEach(([key, val]) => {
            const input = document.querySelector('[name="default_' + key + '"]');
            if (input) input.value = val;
        });
    }
    // Fill column mapping (need contract to be selected first)
    if (record.column_mapping && Object.keys(record.column_mapping).length > 0) {
        window._pendingMapping = record.column_mapping;
    }
    showToast('已加载: ' + record.name);
}

async function loadAllDefaults() {
    try {
        const resp = await fetch('/api/excel-bill/defaults');
        const data = await resp.json();
        const items = data.defaults || [];
        const menu = document.getElementById('savedDefaultsMenu');
        menu.querySelectorAll('li:not(.menu-title)').forEach(li => li.remove());

        if (items.length === 0) {
            appendEmptyDefaultsItem(menu);
        } else {
            items.forEach(item => {
                const presetName = (item.preset_key === 'standard_pr' ? '标准' :
                    item.preset_key === 'rd_pr' ? '科研' :
                    item.preset_key === 'simple_pr' ? '简易' : '服务');
                appendDefaultsItem(menu, item, presetName);
            });
        }
    } catch (e) {
        console.error('Load all defaults failed:', e);
    }
}

// Refresh saved list when preset changes
const origSelectPreset = selectPreset;
selectPreset = function(key, el) {
    origSelectPreset(key, el);
    loadSavedDefaultsList();
};

document.addEventListener('click', function(event) {
    const control = event.target.closest('[data-bill-action]');
    if (!control) return;
    const action = control.dataset.billAction;
    if (action === 'select-preset') selectPreset(control.dataset.preset, control);
    if (action === 'show-save') showSaveDialog();
    if (action === 'toggle-contract') toggleContractSection();
    if (action === 'close-save') document.getElementById('saveDialog').close();
    if (action === 'save-defaults') saveDefaults();
    if (action === 'preview') previewData();
    if (action === 'load-defaults') loadDefaults(control.dataset.filename);
    if (action === 'load-all-defaults') loadAllDefaults();
});
document.addEventListener('change', function(event) {
    if (event.target.dataset.billAction === 'contract-change') onContractChange();
});
