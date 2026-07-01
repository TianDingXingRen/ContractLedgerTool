/**
 * editor.js - 合同填写页面的表格编辑器和交互逻辑
 * 由 editor.html 加载，依赖 window.CT_fields 等全局变量
 */
'use strict';

    // ── Progress ──
    function onFieldChange(id) {
        const item = document.getElementById('field_' + id);
        const input = item.querySelector('.field-input, .field-select, textarea');
        if (input && input.value.trim()) {
            item.classList.add('filled');
            item.dataset.filled = '1';
        } else {
            item.classList.remove('filled');
            item.dataset.filled = '0';
        }
        const nav = document.querySelector('[data-nav-field="' + id + '"]');
        if (nav) nav.classList.toggle('text-success', item.dataset.filled === '1');
        updateProgress();
    }

    function updateProgress() {
        let filled = 0;
        document.querySelectorAll('.field-item').forEach(item => {
            if (item.classList.contains('field-calc')) return;
            if (item.querySelector('.table-editor')) {
                const tbody = item.querySelector('tbody');
                const tableFilled = !!(tbody && tbody.querySelectorAll('tr').length > 0);
                item.dataset.filled = tableFilled ? '1' : '0';
                if (tableFilled) { filled++; return; }
            }
            const input = item.querySelector('.field-input, .field-select, textarea');
            const isFilled = !!(input && input.value.trim());
            item.dataset.filled = isFilled ? '1' : '0';
            if (isFilled) filled++;
        });
        filledCount.textContent = filled;
        const pct = totalFields > 0 ? Math.round((filled / totalFields) * 100) : 0;
        progressFill.style.width = pct + '%';

        // 更新过滤按钮计数
        var requiredCount = 0, emptyCount = 0, calcCount = 0;
        document.querySelectorAll('.field-item').forEach(function(item) {
            if (item.classList.contains('field-calc')) { calcCount++; return; }
            if (item.dataset.required === '1') requiredCount++;
            if (item.dataset.filled !== '1') emptyCount++;
        });
        var elReq = document.getElementById('countRequired');
        if (elReq) elReq.textContent = requiredCount;
        var elEmp = document.getElementById('countEmpty');
        if (elEmp) elEmp.textContent = emptyCount;
        var elCalc = document.getElementById('countCalc');
        if (elCalc) elCalc.textContent = calcCount;
    }

    function bindEditorFilters() {
        document.querySelectorAll('.editor-filter').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setEditorFilter(btn.dataset.filter || 'all');
            });
        });
    }

    function setEditorFilter(filter) {
        document.querySelectorAll('.editor-filter').forEach(function(btn) {
            btn.classList.toggle('btn-primary', btn.dataset.filter === filter);
            btn.classList.toggle('btn-ghost', btn.dataset.filter !== filter);
        });
        document.querySelectorAll('.field-item').forEach(function(item) {
            var visible = true;
            if (filter === 'required') visible = item.dataset.required === '1';
            if (filter === 'empty') visible = item.dataset.filled !== '1' && !item.classList.contains('field-calc');
            if (filter === 'calc') visible = item.dataset.fieldType === 'calculated';
            item.classList.toggle('hidden', !visible);
            const nav = document.querySelector('[data-nav-field="' + item.id.replace('field_', '') + '"]');
            if (nav) nav.classList.toggle('hidden', !visible);
        });
    }

    // ── Table editor ──
    function initTable(fid) {
        // 防御：fid 无效时静默退出（兼容缺少 id 的旧模板）
        if (fid == null || fid === '' || fid === undefined) {
            console.warn('initTable: 无效的表格字段 ID，跳过初始化');
            return;
        }
        initTableColumns(fid);
        const defaultsEl = document.getElementById('table_default_rows_' + fid);
        const defaultsRaw = defaultsEl ? defaultsEl.value : '[]';
        let defaultRows = [];
        try { defaultRows = JSON.parse(defaultsRaw || '[]'); } catch(e) {}
        if (Array.isArray(defaultRows) && defaultRows.length > 0) {
            defaultRows.forEach(row => addTableRow(fid, row));
        } else {
            addTableRow(fid);
        }
    }

    function initTableColumns(fid) {
        const el = document.getElementById('table_columns_' + fid);
        if (!el) {
            console.warn('initTableColumns: 找不到表格列定义元素 table_columns_' + fid);
            columnsData[fid] = [];
            return;
        }
        const raw = el.value;
        columnsData[fid] = JSON.parse(raw);
        renderTableHeader(fid);
    }

    function renderTableHeader(fid) {
        const cols = columnsData[fid] || [];
        let html = '<tr><th class="row-num-col w-10 text-center">#</th>';
        cols.forEach(function(col, ci) {
            html += '<th class="bg-base-200">';
            html += '<span class="th-wrap inline-flex items-center gap-1">';
            html += '<input type="text" class="th-input input input-ghost input-xs w-20 font-semibold" value="' + escapeHtml(col.label) + '" onchange="updateColumnLabel(' + fid + ',' + ci + ',this.value)">';
            html += '<code class="var-code table-var-code badge badge-xs font-mono">' + escapeHtml(col.key || ('col_' + ci)) + '</code>';
            if (col.field_type === 'calculated') {
                html += ' <span class="calc-tag badge badge-warning badge-xs">自动</span>';
            }
            html += '<button type="button" class="th-del-btn btn btn-ghost btn-xs px-1 text-base-content/30 hover:text-error" onclick="removeTableColumnAt(' + fid + ',' + ci + ')">&times;</button>';
            html += '</span></th>';
        });
        html += '<th class="row-action-col w-10"></th></tr>';
        document.getElementById('table_head_' + fid).innerHTML = html;
        syncColumnsInput(fid);
    }

    function addTableColumn(fid) {
        var cols = columnsData[fid];
        if (!cols || !Array.isArray(cols)) {
            console.warn('addTableColumn: 表格列数据无效, fid=' + fid);
            return;
        }
        var ci = cols.length;
        var newKey = generateColumnKey(fid);
        cols.push({key: newKey, label: '新列' + (ci + 1), field_type: 'text', formula: ''});
        renderTableHeader(fid);
        var colDef = cols[ci];
        var tbody = document.getElementById('table_body_' + fid);
        tbody.querySelectorAll('tr').forEach(function(tr) {
            var rowIdx = parseInt(tr.dataset.rowIndex);
            var td = document.createElement('td');
            if (colDef.field_type === 'calculated') {
                td.innerHTML = '<span class="calc-cell" id="tcalc_' + fid + '_' + rowIdx + '_' + ci + '">0</span>';
                td.dataset.formula = colDef.formula || '';
                td.dataset.colKey = newKey;
                td.dataset.rowIdx = rowIdx;
            } else {
                var inp = document.createElement('input');
                inp.type = 'text';
                inp.className = 'table-cell-input input input-ghost input-xs w-full';
                inp.dataset.colKey = newKey;
                inp.dataset.rowIdx = rowIdx;
                inp.placeholder = colDef.label;
                inp.oninput = function() {
                    recalcTableRow(fid, parseInt(this.dataset.rowIdx));
                    updateTableData(fid);
                    updateProgress();
                };
                td.appendChild(inp);
            }
            tr.insertBefore(td, tr.lastElementChild);
        });
        syncColumnsInput(fid);
        updateTableData(fid);
    }

    function removeTableColumn(fid) {
        var cols = columnsData[fid];
        if (!cols || !Array.isArray(cols) || cols.length <= 1) return;
        removeTableColumnAt(fid, cols.length - 1);
    }

    async function removeTableColumnAt(fid, ci) {
        var cols = columnsData[fid];
        if (!cols || !Array.isArray(cols) || cols.length <= 1) return;
        var colName = (cols[ci] && cols[ci].label) || ('第' + (ci + 1) + '列');
        var ok = await window.confirmAction('确定删除列「' + colName + '」及其所有数据吗？此操作不可撤销。', {
            title: '删除表格列',
            confirmText: '删除',
            danger: true,
        });
        if (!ok) return;
        cols.splice(ci, 1);
        renderTableHeader(fid);
        var tbody = document.getElementById('table_body_' + fid);
        tbody.querySelectorAll('tr').forEach(function(tr) {
            var td = tr.children[ci + 1];
            if (td) tr.removeChild(td);
        });
        syncColumnsInput(fid);
        updateTableData(fid);
    }

    function updateColumnLabel(fid, ci, label) {
        var cols = columnsData[fid];
        if (cols[ci]) { cols[ci].label = label; }
        var tbody = document.getElementById('table_body_' + fid);
        tbody.querySelectorAll('tr').forEach(function(tr) {
            var inp = tr.children[ci + 1] ? tr.children[ci + 1].querySelector('.table-cell-input') : null;
            if (inp) inp.placeholder = label;
        });
        syncColumnsInput(fid);
    }

    function generateColumnKey(fid) {
        var existing = {};
        (columnsData[fid] || []).forEach(function(c) { existing[c.key] = true; });
        var idx = 0;
        while (existing['col_' + idx]) idx++;
        return 'col_' + idx;
    }

    function syncColumnsInput(fid) {
        var el = document.getElementById('table_cols_input_' + fid);
        if (el) {
            el.value = JSON.stringify(columnsData[fid] || []);
        }
    }

    function addTableRow(fid, rowData) {
        const tbody = document.getElementById('table_body_' + fid);
        if (!tbody) {
            console.warn('addTableRow: 找不到表格 body table_body_' + fid);
            return;
        }
        const columns = columnsData[fid] || [];
        const rowIdx = tbody.querySelectorAll('tr').length;
        rowData = rowData || {};
        const tr = document.createElement('tr');
        tr.dataset.rowIndex = rowIdx;
        // Row number
        const numTd = document.createElement('td');
        numTd.className = 'row-num text-center text-xs text-base-content/40';
        numTd.textContent = rowIdx + 1;
        tr.appendChild(numTd);
        // Data columns
        columns.forEach((col, ci) => {
            const td = document.createElement('td');
            if (col.field_type === 'calculated') {
                td.innerHTML = `<span class="calc-cell text-warning font-medium text-right block min-w-[60px] px-2" id="tcalc_${fid}_${rowIdx}_${ci}">0</span>`;
                td.dataset.formula = col.formula || '';
                td.dataset.colKey = col.key;
                td.dataset.rowIdx = rowIdx;
            } else {
                const inp = col.field_type === 'textarea'
                    ? document.createElement('textarea')
                    : (col.field_type === 'select' ? document.createElement('select') : document.createElement('input'));
                if (inp.tagName === 'INPUT') {
                    inp.type = col.field_type === 'number' ? 'number' : 'text';
                    if (col.field_type === 'number') inp.step = 'any';
                }
                inp.className = 'table-cell-input input input-ghost input-xs w-full';
                inp.dataset.colKey = col.key;
                inp.dataset.rowIdx = rowIdx;
                inp.placeholder = col.label;
                if (col.field_type === 'select') {
                    const blank = document.createElement('option');
                    blank.value = ''; blank.textContent = '— 请选择 —';
                    inp.appendChild(blank);
                    (col.options || []).forEach(function(optionValue) {
                        const option = document.createElement('option');
                        option.value = optionValue; option.textContent = optionValue;
                        inp.appendChild(option);
                    });
                }
                inp.value = rowData[col.key] != null ? rowData[col.key] : (col.default_value || '');
                const handleInput = function() {
                    recalcTableRow(fid, parseInt(this.dataset.rowIdx));
                    updateTableData(fid);
                    updateProgress();
                };
                inp.oninput = handleInput;
                inp.onchange = handleInput;
                td.appendChild(inp);
            }
            tr.appendChild(td);
        });
        // Delete button
        const actionTd = document.createElement('td');
        actionTd.innerHTML = '<button type="button" class="btn btn-ghost btn-xs text-error" onclick="removeThisRow(this)"><i data-lucide="x" class="w-3 h-3"></i></button>';
        tr.appendChild(actionTd);
        tbody.appendChild(tr);
        // icons auto-rendered by icons.js
        recalcTableRow(fid, rowIdx);
        updateTableData(fid);
        updateProgress();
    }

    function removeTableRow(fid) {
        const tbody = document.getElementById('table_body_' + fid);
        if (!tbody) return;
        if (tbody.querySelectorAll('tr').length <= 1) return;
        tbody.removeChild(tbody.lastElementChild);
        updateTableData(fid);
        renumberRows(fid);
        updateProgress();
    }

    function removeThisRow(btn) {
        const tr = btn.closest('tr');
        const tbody = tr.parentElement;
        if (tbody.querySelectorAll('tr').length <= 1) return;
        tbody.removeChild(tr);
        const fid = parseInt(tbody.id.replace('table_body_', ''));
        updateTableData(fid);
        renumberRows(fid);
        updateProgress();
    }

    function renumberRows(fid) {
        const tbody = document.getElementById('table_body_' + fid);
        tbody.querySelectorAll('tr').forEach((tr, i) => {
            tr.querySelector('.row-num').textContent = i + 1;
            tr.dataset.rowIndex = i;
            tr.querySelectorAll('[data-row-idx]').forEach(el => el.dataset.rowIdx = i);
        });
    }

    function recalcTableRow(fid, rowIdx) {
        const tbody = document.getElementById('table_body_' + fid);
        const tr = tbody.querySelector(`tr[data-row-index="${rowIdx}"]`);
        if (!tr) return;
        const columns = columnsData[fid] || [];
        const context = {};
        tr.querySelectorAll('.table-cell-input').forEach(inp => {
            const val = parseFloat(inp.value) || 0;
            context[inp.dataset.colKey] = val;
        });
        tr.querySelectorAll('[data-formula]').forEach(td => {
            const formula = td.dataset.formula;
            if (!formula) return;
            try {
                const result = safeEval(formula, context);
                td.textContent = result.toFixed(2);
            } catch(e) { td.textContent = '?'; }
        });
    }

    function updateTableData(fid) {
        const tbody = document.getElementById('table_body_' + fid);
        if (!tbody) return;
        const columns = columnsData[fid] || [];
        const rows = [];
        tbody.querySelectorAll('tr').forEach(tr => {
            const row = {};
            tr.querySelectorAll('.table-cell-input').forEach(inp => {
                row[inp.dataset.colKey] = inp.value;
            });
            tr.querySelectorAll('[data-formula]').forEach(td => {
                row[td.dataset.colKey] = td.textContent;
            });
            if (Object.keys(row).length > 0) rows.push(row);
        });
        document.getElementById('table_data_' + fid).value = JSON.stringify(rows);
        if (typeof triggerCalc === 'function') triggerCalc(fid);
    }

    // ── Excel 粘贴支持：将表格 cell input 的 paste 事件拦截并分发到多单元格 ──
    document.addEventListener('paste', function(e) {
        const target = e.target;
        if (!target.classList.contains('table-cell-input')) return;

        const text = (e.clipboardData || window.clipboardData).getData('text');
        // 只有含 tab 或换行的多单元格数据才拦截
        if (text.indexOf('\t') === -1 && text.indexOf('\n') === -1) return;

        e.preventDefault();
        // 解析为二维数组
        const lines = text.split(/\r?\n/).filter(function(l, i, arr) {
            // 去掉末尾空行
            return i < arr.length - 1 || l.trim() !== '';
        });
        if (lines.length === 0) return;
        const data = lines.map(function(l) { return l.split('\t'); });

        const td = target.closest('td');
        const tr = td ? td.closest('tr') : null;
        const tbody = tr ? tr.closest('tbody') : null;
        if (!tbody) return;
        const fid = parseInt(tbody.id.replace('table_body_', ''));
        const columns = columnsData[fid] || [];

        // 找到起始行列
        const startRow = parseInt(tr.dataset.rowIndex);
        const startColKey = target.dataset.colKey;
        var startCol = -1;
        for (var ci = 0; ci < columns.length; ci++) {
            if (columns[ci].key === startColKey) { startCol = ci; break; }
        }
        if (startCol < 0) return;

        // 跳过公式列
        const editableCols = [];
        columns.forEach(function(col, ci) {
            if (col.field_type !== 'calculated') editableCols.push(ci);
        });

        // 确保有足够的行
        const existingRows = tbody.querySelectorAll('tr').length;
        const neededRows = startRow + data.length;
        for (var r = existingRows; r < neededRows; r++) {
            addTableRow(fid);
        }

        // 填充数据（从起始单元格开始，向下、向右扩展）
        for (var dr = 0; dr < data.length; dr++) {
            const rowIdx = startRow + dr;
            const tr2 = tbody.querySelector('tr[data-row-index="' + rowIdx + '"]');
            if (!tr2) continue;
            for (var dc = 0; dc < data[dr].length; dc++) {
                const colIdx = startCol + dc;
                if (colIdx >= columns.length) break;
                if (columns[colIdx].field_type === 'calculated') continue;
                const inp = tr2.querySelector('.table-cell-input[data-col-key="' + columns[colIdx].key + '"]');
                if (inp) {
                    inp.value = data[dr][dc];
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
        }
        // 批量更新后统一触发 recalc、renumber 和 progress
        if (data.length > 1 || startRow + data.length > existingRows) {
            renumberRows(fid);
        }
        recalcTableRow(fid, startRow);
        updateTableData(fid);
        updateProgress();
    });

    // ── Calculated fields (from formula-engine.js) ──
    var triggerCalc = window.CT_triggerCalc;
    var recalcField = window.CT_recalcField;
    var recalcAllFields = window.CT_recalcAllFields;

    // ── Safe eval (from formula-engine.js) ──
    var safeEval = window.CT_safeEval;

    // ── Save defaults ──
    document.getElementById('saveDefaultsBtn').addEventListener('click', function() {
        var btn = this;
        var originalText = btn.innerHTML;
        Object.keys(columnsData).forEach(function(fid) {
            try { syncColumnsInput(parseInt(fid)); updateTableData(parseInt(fid)); } catch(e) {}
        });
        btn.disabled = true;
        btn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> 保存中…';
        fetch(window.CT_saveDefaultsUrl, {
            method: 'POST',
            body: new FormData(document.getElementById('editorForm'))
        })
        .then(function(response) {
            return response.json().then(function(data) {
                if (!response.ok || !data.success) throw new Error(data.message || '保存失败');
                return data;
            });
        })
        .then(function(data) { showToast(data.message || '预制内容已保存', 'success'); })
        .catch(function(err) { showToast(err.message || '保存失败', 'error'); console.error(err); })
        .finally(function() { btn.disabled = false; btn.innerHTML = originalText; });
    });

    var pendingPreflight = null;

    function generationActionUrl(isBatch, form) {
        return isBatch ? window.CT_generateBatchUrl : form.action;
    }

    function runPreflight(form, isBatch) {
        var formData = new FormData(form);
        formData.append('_generation_mode', isBatch ? 'batch' : 'single');
        return fetch(window.CT_generatePreflightUrl, { method: 'POST', body: formData })
            .then(function(response) {
                return response.text().then(function(text) {
                    var payload;
                    try {
                        payload = JSON.parse(text || '{}');
                    } catch(e) {
                        payload = {
                            ok: false,
                            blocking: [text.substring(0, 300) || '生成前复核失败'],
                            warnings: []
                        };
                    }
                    payload._statusOk = response.ok;
                    return payload;
                });
            });
    }

    function listHtml(items) {
        return (items || []).map(function(item) {
            return '<li>' + escapeHtml(item) + '</li>';
        }).join('');
    }

    function preflightSummary(payload) {
        var s = payload.summary || {};
        if (payload.mode === 'batch') {
            var names = (s.counterparties_preview || []).join('、');
            return '将基于「' + (s.template || '当前模板') + '」批量生成 ' + (s.count || 0) +
                ' 份合同' + (names ? '：' + names + ((s.count || 0) > 5 ? ' 等' : '') : '') + '。';
        }
        var parts = ['模板：' + (s.template || '当前模板')];
        if (s.contract_no) parts.push('编号：' + s.contract_no);
        if (s.counterparty) parts.push('对方：' + s.counterparty);
        if (s.amount !== null && s.amount !== undefined && s.amount !== '') parts.push('金额：' + s.amount);
        if (s.sign_date) parts.push('日期：' + s.sign_date);
        return parts.join('，') + '。';
    }

    function showPreflightPanel(payload) {
        var panel = document.getElementById('preflightPanel');
        var summary = document.getElementById('preflightSummaryText');
        var blockingWrap = document.getElementById('preflightBlockingWrap');
        var warningWrap = document.getElementById('preflightWarningWrap');
        var blockingList = document.getElementById('preflightBlockingList');
        var warningList = document.getElementById('preflightWarningList');
        var confirmBtn = document.getElementById('preflightConfirmBtn');
        var blocking = payload.blocking || [];
        var warnings = payload.warnings || [];

        summary.textContent = preflightSummary(payload);
        blockingList.innerHTML = listHtml(blocking);
        warningList.innerHTML = listHtml(warnings);
        blockingWrap.classList.toggle('hidden', blocking.length === 0);
        warningWrap.classList.toggle('hidden', warnings.length === 0);
        confirmBtn.classList.toggle('hidden', blocking.length > 0);
        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function setGenerating(btn, text) {
        btn.disabled = true;
        btn.innerHTML = text;
    }

    function resetGenerateButton(btn, origText) {
        btn.disabled = false;
        btn.innerHTML = origText;
    }

    function performGeneration(form, actionUrl, btn, origText, overlay) {
        Object.keys(columnsData).forEach(function(fid) {
            try { syncColumnsInput(parseInt(fid)); } catch(e) {}
        });
        var formData = new FormData(form);
        setGenerating(btn, '<span class="loading loading-spinner"></span> 生成中…');
        overlay.classList.add('active');

        fetch(actionUrl, { method: 'POST', body: formData })
        .then(function(response) {
            if (!response.ok) {
                return response.text().then(function(text) {
                    throw new Error(text.substring(0, 300) || '服务器错误');
                });
            }
            var contentType = response.headers.get('Content-Type') || '';
            var isDocx = contentType.indexOf('officedocument') !== -1 || contentType.indexOf('octet-stream') !== -1;
            var isZip = contentType.indexOf('zip') !== -1;
            if (!isDocx && !isZip) {
                return response.text().then(function(text) {
                    throw new Error('服务器返回了意外的响应类型，请刷新页面后重试');
                });
            }
            var disposition = response.headers.get('Content-Disposition') || '';
            var detailUrl = response.headers.get('X-Contract-Detail-Url') || '';
            var pdfUrl = response.headers.get('X-PDF-Url') || '';
            var genErrors = response.headers.get('X-Generation-Errors') || '';
            var ledgerError = response.headers.get('X-Ledger-Error') || '';
            var filename = isZip ? '批量合同.zip' : '合同.docx';
            var match = disposition.match(/filename\*?=(?:UTF-8'')?([^;\s"']+)/i);
            if (match) { try { filename = decodeURIComponent(match[1]); } catch(e) {} }
            return response.blob().then(function(blob) {
                return { blob: blob, filename: filename, detailUrl: detailUrl, pdfUrl: pdfUrl,
                         isBatch: isZip, genErrors: genErrors, ledgerError: ledgerError };
            });
        })
        .then(function(result) {
            var url = window.URL.createObjectURL(result.blob);
            var a = document.createElement('a');
            a.href = url; a.download = result.filename;
            document.body.appendChild(a); a.click(); a.remove();
            if (result.pdfUrl) {
                var pdfFrame = document.createElement('iframe');
                pdfFrame.style.display = 'none';
                pdfFrame.src = result.pdfUrl;
                document.body.appendChild(pdfFrame);
                setTimeout(function() { document.body.removeChild(pdfFrame); }, 5000);
            }
            overlay.classList.remove('active');
            resetGenerateButton(btn, origText);
            if (result.genErrors) {
                showToast('部分合同生成出错：' + result.genErrors, 'error');
            } else if (result.ledgerError) {
                showToast(result.ledgerError, 'error');
            } else {
                showToast(result.isBatch ? '批量合同已生成' : '合同已生成', 'success');
            }
            showGenerationResult(result, url);
        })
        .catch(function(err) {
            overlay.classList.remove('active');
            resetGenerateButton(btn, origText);
            showToast(err.message || '生成失败', 'error');
            console.error(err);
        });
    }

    // ── Form submit ──
    document.getElementById('editorForm').addEventListener('submit', function(e) {
        e.preventDefault();
        var overlay = document.getElementById('loadingOverlay');
        var btn = document.getElementById('generateBtn');
        var origText = btn.innerHTML;

        var projectInput = document.getElementById('projectName');
        var coverageStartInput = document.getElementById('coverageStart');
        var coverageEndInput = document.getElementById('coverageEnd');
        var projectName = projectInput ? projectInput.value.trim() : '';
        var coverageStart = coverageStartInput ? coverageStartInput.value.trim() : '';
        var coverageEnd = coverageEndInput ? coverageEndInput.value.trim() : '';
        if ((coverageStart && !coverageEnd) || (!coverageStart && coverageEnd)) {
            showToast('覆盖范围的起始号和结束号需要同时填写', 'error');
            (coverageStart ? coverageEndInput : coverageStartInput).focus();
            return;
        }
        if ((coverageStart || coverageEnd) && !projectName) {
            showToast('填写覆盖范围前，请先填写所属项目', 'error');
            projectInput.focus();
            return;
        }
        if (coverageStart && coverageEnd && Number(coverageStart) > Number(coverageEnd)) {
            showToast('覆盖范围起始号不能大于结束号', 'error');
            coverageStartInput.focus();
            return;
        }

        const emptyFields = [];
        const requiredEmpty = [];
        document.querySelectorAll('.field-item').forEach(function(item) {
            if (item.classList.contains('field-calc')) return;
            if (item.querySelector('.table-editor')) {
                var tbody = item.querySelector('tbody');
                if (!tbody || tbody.querySelectorAll('tr').length === 0) {
                    emptyFields.push(item.querySelector('.field-label').textContent.trim());
                    if (item.dataset.required === '1') requiredEmpty.push(item.querySelector('.field-label').textContent.trim());
                }
                return;
            }
            var input = item.querySelector('.field-input, .field-select, textarea');
            if (input && !input.value.trim()) {
                emptyFields.push(item.querySelector('.field-label').textContent.trim());
                if (item.dataset.required === '1') requiredEmpty.push(item.querySelector('.field-label').textContent.trim());
            }
        });
        if (emptyFields.length > 0 && emptyFields.length === totalFields - document.querySelectorAll('.field-calc').length) {
            showToast('请至少填写一个字段后再生成', 'error');
            return;
        }
        if (requiredEmpty.length > 0) {
            showToast(requiredEmpty.length + ' 个必填字段未填写：' + requiredEmpty.slice(0, 5).join('、') + (requiredEmpty.length > 5 ? ' 等' : ''), 'error');
            var firstRequired = document.querySelector('.field-item[data-required="1"][data-filled="0"]');
            if (firstRequired) firstRequired.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        Object.keys(columnsData).forEach(function(fid) {
            try { syncColumnsInput(parseInt(fid)); } catch(e) {}
        });

        var form = e.target;

        // Batch mode: POST to /generate-batch, handle zip
        var isBatch = document.getElementById('batchToggle') && document.getElementById('batchToggle').checked;
        var actionUrl = generationActionUrl(isBatch, form);
        setGenerating(btn, '<span class="loading loading-spinner"></span> 检查中…');

        runPreflight(form, isBatch)
            .then(function(payload) {
                var blocking = payload.blocking || [];
                var warnings = payload.warnings || [];
                if (blocking.length || warnings.length) {
                    pendingPreflight = blocking.length ? null : {
                        form: form,
                        actionUrl: actionUrl,
                        btn: btn,
                        origText: origText,
                        overlay: overlay
                    };
                    showPreflightPanel(payload);
                    resetGenerateButton(btn, origText);
                    return;
                }
                performGeneration(form, actionUrl, btn, origText, overlay);
            })
            .catch(function(err) {
                resetGenerateButton(btn, origText);
                showToast(err.message || '生成前复核失败', 'error');
                console.error(err);
            });
    });

    document.getElementById('preflightConfirmBtn').addEventListener('click', function() {
        if (!pendingPreflight) return;
        document.getElementById('preflightPanel').classList.add('hidden');
        var pending = pendingPreflight;
        pendingPreflight = null;
        performGeneration(pending.form, pending.actionUrl, pending.btn, pending.origText, pending.overlay);
    });

    document.getElementById('preflightCloseBtn').addEventListener('click', function() {
        pendingPreflight = null;
        document.getElementById('preflightPanel').classList.add('hidden');
    });

    function showGenerationResult(result, blobUrl) {
        if (currentGeneratedUrl) {
            window.URL.revokeObjectURL(currentGeneratedUrl);
        }
        currentGeneratedUrl = blobUrl;

        // 清除草稿（生成成功后无需保留）
        if (typeof window.clearDraft === 'function') {
            window.clearDraft();
        }

        const panel = document.getElementById('generationResultPanel');
        const downloadLink = document.getElementById('resultDownloadLink');
        const detailLink = document.getElementById('resultDetailLink');
        const pdfLink = document.getElementById('resultPdfLink');
        const resultText = document.getElementById('generationResultText');

        downloadLink.href = blobUrl;
        downloadLink.download = result.filename || (result.isBatch ? '批量合同.zip' : '合同.docx');
        resultText.textContent = result.isBatch
            ? '批量合同已开始下载，可在这里重新下载生成文件。'
            : '合同已开始下载，可查看详情或继续填写。';

        if (!result.isBatch && result.detailUrl) {
            detailLink.href = result.detailUrl;
            detailLink.classList.remove('hidden');
        } else {
            detailLink.classList.add('hidden');
        }

        if (result.pdfUrl) {
            pdfLink.href = result.pdfUrl;
            pdfLink.classList.remove('hidden');
        } else {
            pdfLink.classList.add('hidden');
        }

        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // icons.js observes dynamic nodes and renders icons automatically.
    }

    document.getElementById('resultContinueBtn').addEventListener('click', function() {
        document.getElementById('generationResultPanel').classList.add('hidden');
    });

    Object.assign(window, {
        onFieldChange,
        updateProgress,
        bindEditorFilters,
        setEditorFilter,
        initTable,
        addTableColumn,
        removeTableColumn,
        removeTableColumnAt,
        updateColumnLabel,
        addTableRow,
        removeTableRow,
        removeThisRow,
        triggerCalc,
        recalcField,
        recalcAllFields,
    });

    updateProgress();

    // ── Tab key: 在字段间跳转 ──
    document.addEventListener('keydown', function(e) {
        if (e.key !== 'Tab') return;
        var active = document.activeElement;
        if (!active || !active.closest) return;
        var isFieldInput = active.closest('.field-item') || active.closest('.table-cell-input') ||
                           active.closest('textarea') || active.closest('select');
        if (!isFieldInput) return;

        var allInputs = [];
        document.querySelectorAll('.field-item').forEach(function(item) {
            if (item.classList.contains('field-calc')) return;
            if (item.classList.contains('hidden')) return;
            var inputs = item.querySelectorAll('input:not([type="hidden"]):not([readonly]), textarea, select');
            inputs.forEach(function(inp) { allInputs.push(inp); });
        });
        if (allInputs.length === 0) return;

        var idx = allInputs.indexOf(active);
        if (idx < 0) return;

        e.preventDefault();
        var next;
        if (e.shiftKey) {
            next = idx > 0 ? allInputs[idx - 1] : allInputs[allInputs.length - 1];
        } else {
            next = idx < allInputs.length - 1 ? allInputs[idx + 1] : allInputs[0];
        }
        next.focus();
        if (next.closest('.table-field-wrap')) {
            next.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        if (next.closest('.field-item')) {
            next.closest('.field-item').scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    });
