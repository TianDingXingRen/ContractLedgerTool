/**
 * editor.js - 合同填写页面的表格编辑器和交互逻辑
 * 核心编辑行为；启动配置、草稿、API、表格事件与预览入口由独立模块提供。
 */
'use strict';

    var editorActiveFieldId = null;
    var assistRenderQueued = false;

    function getPreviewFields() {
        return editorConfig.fields || [];
    }

    function getPreviewBlocks() {
        return editorConfig.previewBlocks || [];
    }

    function normalizeFieldId(id) {
        return id === null || id === undefined ? '' : String(id);
    }

    function getFieldItem(id) {
        return document.getElementById('field_' + normalizeFieldId(id));
    }

    function getFieldInput(id) {
        var item = getFieldItem(id);
        if (!item) return null;
        return item.querySelector('.field-input, .field-select, textarea');
    }

    function getFieldMeta(id) {
        var fid = normalizeFieldId(id);
        return getPreviewFields().find(function(field) {
            return normalizeFieldId(field.id) === fid;
        }) || null;
    }

    function getFieldTypeLabel(type) {
        var labels = {
            text: '单行',
            number: '数字',
            textarea: '多行',
            select: '选择',
            table: '表格',
            calculated: '自动'
        };
        return labels[type] || type || '字段';
    }

    function getTableColumns(id) {
        var fid = normalizeFieldId(id);
        if (columnsData && columnsData[fid]) return columnsData[fid];
        var meta = getFieldMeta(fid);
        return (meta && meta.columns) || [];
    }

    function getTableRows(id) {
        var dataEl = document.getElementById('table_data_' + normalizeFieldId(id));
        if (!dataEl) return [];
        try {
            var rows = JSON.parse(dataEl.value || '[]');
            return Array.isArray(rows) ? rows : [];
        } catch(e) {
            return [];
        }
    }

    function rowHasContent(row) {
        return Object.keys(row || {}).some(function(key) {
            return String(row[key] == null ? '' : row[key]).trim() !== '';
        });
    }

    function tableFieldHasContent(id) {
        return getTableRows(id).some(rowHasContent);
    }

    function fieldHasValue(field) {
        if (!field) return false;
        if (field.field_type === 'table') {
            return tableFieldHasContent(field.id);
        }
        var input = getFieldInput(field.id);
        return !!(input && String(input.value || '').trim());
    }

    function fieldValueText(field) {
        var input = getFieldInput(field.id);
        return input ? String(input.value || '') : '';
    }

    function fieldTypeBadgeClass(field) {
        if (field.required && !fieldHasValue(field)) return 'badge-error';
        if (fieldHasValue(field)) return 'badge-success';
        if (field.field_type === 'calculated') return 'badge-warning';
        return 'badge-ghost';
    }

    function nl2br(text) {
        return escapeHtml(text).replace(/\n/g, '<br>');
    }

    function previewPlaceholderText(field, tableMode) {
        var prefix = field.required ? '必填' : '待填写';
        return tableMode ? prefix + '表格：' + (field.label || field.key || '') : prefix + '：' + (field.label || field.key || '');
    }

    function renderPreviewValue(field) {
        if (field.field_type === 'table') return renderPreviewTable(field);
        var value = fieldValueText(field).trim();
        if (!value) {
            return '<span class="preview-placeholder">【' + escapeHtml(previewPlaceholderText(field, false)) + '】</span>';
        }
        return '<span class="preview-value">' + nl2br(value) + '</span>';
    }

    function renderPreviewTable(field) {
        var columns = getTableColumns(field.id);
        var rows = getTableRows(field.id).filter(rowHasContent);
        if (!columns.length) {
            return '<div class="preview-placeholder">【表格列待配置】</div>';
        }
        if (!rows.length) {
            return '<div class="preview-placeholder">【' + escapeHtml(previewPlaceholderText(field, true)) + '】</div>';
        }
        var head = columns.map(function(col) {
            return '<th>' + escapeHtml(col.label || col.key || '') + '</th>';
        }).join('');
        var body = rows.slice(0, 6).map(function(row) {
            return '<tr>' + columns.map(function(col) {
                return '<td>' + escapeHtml(row[col.key] == null ? '' : row[col.key]) + '</td>';
            }).join('') + '</tr>';
        }).join('');
        var more = rows.length > 6 ? '<div class="contract-preview-more">还有 ' + (rows.length - 6) + ' 行未展开</div>' : '';
        return '<div class="preview-table-mock overflow-x-auto"><table class="contract-preview-table"><thead><tr>' +
            head + '</tr></thead><tbody>' + body + '</tbody></table></div>' + more;
    }

    function sanitizeCssFontFamily(name) {
        return String(name || '').replace(/["';{}]/g, '').trim();
    }

    function styleFromFormat(format, extra) {
        var fmt = format || {};
        var styles = [];
        if (fmt.font_size_pt) styles.push('font-size:' + Number(fmt.font_size_pt).toFixed(2) + 'pt');
        if (fmt.bold) styles.push('font-weight:700');
        if (fmt.font_family) {
            var family = sanitizeCssFontFamily(fmt.font_family);
            if (family) styles.push('font-family:' + family + ', SimSun, FangSong, serif');
        }
        if (fmt.left_indent_pt) styles.push('margin-left:' + Number(fmt.left_indent_pt).toFixed(2) + 'pt');
        if (fmt.first_line_indent_pt) styles.push('text-indent:' + Number(fmt.first_line_indent_pt).toFixed(2) + 'pt');
        if (fmt.space_before_pt) styles.push('margin-top:' + Number(fmt.space_before_pt).toFixed(2) + 'pt');
        if (fmt.space_after_pt) styles.push('margin-bottom:' + Number(fmt.space_after_pt).toFixed(2) + 'pt');
        if (fmt.line_pt) styles.push('line-height:' + Number(fmt.line_pt).toFixed(2) + 'pt');
        if (fmt.align) styles.push('text-align:' + escapeHtml(fmt.align));
        if (extra) styles.push(extra);
        return styles.length ? ' style="' + styles.join(';') + '"' : '';
    }

    function tableColgroup(grid) {
        if (!grid || !grid.length) return '';
        var total = grid.reduce(function(sum, width) { return sum + Math.max(1, Number(width) || 1); }, 0);
        if (!total) return '';
        return '<colgroup>' + grid.map(function(width) {
            var pct = (Math.max(1, Number(width) || 1) / total) * 100;
            return '<col style="width:' + pct.toFixed(3) + '%">';
        }).join('') + '</colgroup>';
    }

    function renderDocumentField(fieldId) {
        var field = getFieldMeta(fieldId);
        if (!field) return '';
        return renderPreviewValue(field);
    }

    function renderPreviewParts(parts) {
        return (parts || []).map(function(part) {
            if (part.kind === 'field') {
                var fid = normalizeFieldId(part.field_id);
                return '<span class="contract-preview-token" data-preview-field="' + escapeHtml(fid) + '">' +
                    renderDocumentField(fid) + '</span>';
            }
            if (part.kind === 'text') {
                return nl2br(part.text || '');
            }
            return '';
        }).join('');
    }

    function renderRepeatPart(part, field, rowData, rowIndex) {
        if (part.kind === 'text') return nl2br(part.text || '');
        if (part.kind === 'row_index') return String(rowIndex + 1);
        if (part.kind !== 'table_column') return '';
        var value = String(rowData && rowData[part.column_key] != null ? rowData[part.column_key] : '').trim();
        if (!value) {
            return '<span class="preview-placeholder">【' + escapeHtml(part.label || part.column_key || '待填写') + '】</span>';
        }
        return '<span class="preview-value">' + nl2br(value) + '</span>';
    }

    function renderRepeatCell(cell, field, rowData, rowIndex) {
        return (cell.parts || []).map(function(part) {
            return renderRepeatPart(part, field, rowData, rowIndex);
        }).join('');
    }

    function renderDocumentTableRow(row) {
        var repeatId = row.repeat_field_id;
        if (repeatId !== null && repeatId !== undefined) {
            var field = getFieldMeta(repeatId);
            var rows = getTableRows(repeatId).filter(rowHasContent);
            if (!rows.length) rows = [{}];
            return rows.map(function(rowData, rowIndex) {
                return '<tr class="contract-preview-repeat-row" data-preview-field="' + escapeHtml(normalizeFieldId(repeatId)) + '">' +
                    (row.cells || []).map(function(cell) {
                        var span = Number(cell.col_span || 1);
                        var spanAttr = span > 1 ? ' colspan="' + span + '"' : '';
                        return '<td' + spanAttr + styleFromFormat(cell.format) + '>' + renderRepeatCell(cell, field, rowData, rowIndex) + '</td>';
                    }).join('') + '</tr>';
            }).join('');
        }
        return '<tr>' + (row.cells || []).map(function(cell) {
            var firstId = cell.field_ids && cell.field_ids.length ? normalizeFieldId(cell.field_ids[0]) : '';
            var attr = firstId ? ' data-preview-field="' + escapeHtml(firstId) + '"' : '';
            var span = Number(cell.col_span || 1);
            var spanAttr = span > 1 ? ' colspan="' + span + '"' : '';
            return '<td' + attr + spanAttr + styleFromFormat(cell.format) + '>' + renderPreviewParts(cell.parts || []) + '</td>';
        }).join('') + '</tr>';
    }

    function blockFieldIds(block) {
        var ids = (block.field_ids || []).map(normalizeFieldId);
        if (block.type === 'table') {
            (block.rows || []).forEach(function(row) {
                if (row.repeat_field_id !== null && row.repeat_field_id !== undefined) {
                    ids.push(normalizeFieldId(row.repeat_field_id));
                }
                (row.cells || []).forEach(function(cell) {
                    (cell.field_ids || []).forEach(function(id) { ids.push(normalizeFieldId(id)); });
                });
            });
        }
        return ids.filter(function(id, index) { return id && ids.indexOf(id) === index; });
    }

    function blockHasMissingRequired(block) {
        return blockFieldIds(block).some(function(id) {
            var field = getFieldMeta(id);
            return field && field.required && !fieldHasValue(field);
        });
    }

    function renderDocumentBlock(block) {
        var ids = blockFieldIds(block);
        var firstId = ids.length ? ids[0] : '';
        var active = editorActiveFieldId && ids.indexOf(editorActiveFieldId) !== -1 ? ' active' : '';
        var missing = blockHasMissingRequired(block) ? ' is-missing' : '';
        var attr = firstId ? ' data-preview-field="' + escapeHtml(firstId) + '" role="button" tabindex="0"' : '';
        if (block.type === 'table') {
            var tableAlign = block.align ? ' align-' + escapeHtml(block.align) : '';
            return '<div class="contract-preview-table-wrap contract-preview-block' + tableAlign + active + missing + '"' + attr + '>' +
                '<table class="contract-preview-table">' + tableColgroup(block.grid) + '<tbody>' +
                (block.rows || []).map(renderDocumentTableRow).join('') +
                '</tbody></table></div>';
        }
        var align = block.align ? ' align-' + escapeHtml(block.align) : '';
        var empty = block.empty ? ' is-empty-paragraph' : '';
        var titleLike = String(block.style || '').toLowerCase().indexOf('title') !== -1 ? ' is-title-paragraph' : '';
        return '<div class="contract-preview-block contract-preview-paragraph' + align + empty + titleLike + active + missing + '"' + attr + styleFromFormat(block.format) + '>' +
            renderPreviewParts(block.parts || []) + '</div>';
    }

    function renderDocumentPreview(blocks) {
        return blocks.map(renderDocumentBlock).join('');
    }

    function fitContractPreviewPage() {
        var frame = document.querySelector('.contract-preview-frame');
        var page = document.querySelector('.contract-preview-page');
        if (!frame || !page) return;
        var available = Math.max(260, frame.clientWidth - 24);
        var baseWidth = 794; // A4 width at 96dpi: 595pt * 96 / 72.
        var zoom = Math.max(0.46, Math.min(0.82, available / baseWidth));
        page.style.setProperty('--contract-preview-zoom', zoom.toFixed(3));
    }

    function renderPreviewCard(field, index) {
        var fid = normalizeFieldId(field.id);
        var before = field.context_before || '';
        var after = field.context_after || '';
        var active = editorActiveFieldId === fid ? ' active' : '';
        var missing = field.required && !fieldHasValue(field);
        var contextHtml;
        if (field.field_type === 'table') {
            contextHtml = '<div class="contract-preview-line"><span class="contract-preview-field-label">' +
                escapeHtml((index + 1) + '. ' + (field.label || field.key || '表格')) + '</span></div>' +
                renderPreviewTable(field);
        } else if (before || after) {
            contextHtml = '<div class="contract-preview-line preview-copy">' +
                '<span class="preview-context">' + escapeHtml(before) + '</span>' +
                renderPreviewValue(field) +
                '<span class="preview-context">' + escapeHtml(after) + '</span>' +
                '</div>';
        } else {
            contextHtml = '<div class="contract-preview-line preview-copy"><span class="contract-preview-field-label">' +
                escapeHtml((index + 1) + '. ' + (field.label || field.key || ('字段' + (index + 1)))) + '</span>' +
                renderPreviewValue(field) + '</div>';
        }
        return '<div class="contract-preview-block' + active + (missing ? ' is-missing' : '') +
            '" data-preview-field="' + escapeHtml(fid) + '" role="button" tabindex="0">' +
            contextHtml + '</div>';
    }

    function renderLivePreview() {
        var list = document.getElementById('livePreviewList');
        if (!list) return;
        var fields = getPreviewFields();
        var blocks = getPreviewBlocks();
        var summary = document.getElementById('livePreviewSummary');
        if (summary) {
            var filled = fields.filter(fieldHasValue).length;
            var missingRequired = fields.filter(function(field) { return field.required && !fieldHasValue(field); }).length;
            summary.textContent = (blocks.length ? '完整合同预览' : '字段预览') + '，已填 ' + filled + '/' + fields.length + '，必填待填 ' + missingRequired;
        }
        if (blocks.length) {
            list.innerHTML = renderDocumentPreview(blocks);
            fitContractPreviewPage();
            return;
        }
        if (!fields.length) {
            list.innerHTML = '<div class="text-sm text-base-content/50">当前模板没有可预览字段。</div>';
            return;
        }
        list.innerHTML = fields.map(renderPreviewCard).join('');
        fitContractPreviewPage();
    }

    function renderMissingFieldList() {
        var list = document.getElementById('missingFieldList');
        var countEl = document.getElementById('requiredMissingCount');
        if (!list || !countEl) return;
        var missing = getPreviewFields().filter(function(field) {
            return field.required && !fieldHasValue(field);
        });
        countEl.textContent = missing.length;
        if (!missing.length) {
            list.innerHTML = '<div class="text-success text-sm">必填字段已全部填写。</div>';
            return;
        }
        list.innerHTML = missing.map(function(field) {
            return '<button type="button" class="missing-field-link" data-missing-field="' +
                escapeHtml(normalizeFieldId(field.id)) + '">' +
                '<span class="font-medium">' + escapeHtml(field.label || field.key || '') + '</span>' +
                '<span class="text-xs text-base-content/50">' + getFieldTypeLabel(field.field_type) + '</span>' +
                '</button>';
        }).join('');
    }

    function renderStructureList() {
        var list = document.getElementById('assistStructureList');
        if (!list) return;
        var fields = getPreviewFields();
        list.innerHTML = fields.map(function(field, index) {
            var fid = normalizeFieldId(field.id);
            var active = editorActiveFieldId === fid ? ' active' : '';
            var filled = fieldHasValue(field);
            return '<button type="button" class="assist-structure-link' + active + '" data-structure-field="' +
                escapeHtml(fid) + '">' +
                '<span class="structure-index">' + (index + 1) + '</span>' +
                '<span class="structure-label">' + escapeHtml(field.label || field.key || '') + '</span>' +
                '<span class="badge badge-xs ' + (filled ? 'badge-success' : (field.required ? 'badge-error' : 'badge-ghost')) + '">' +
                (filled ? '已填' : (field.required ? '待填' : getFieldTypeLabel(field.field_type))) + '</span>' +
                '</button>';
        }).join('');
    }

    function renderActiveFieldContext() {
        var box = document.getElementById('activeFieldContext');
        if (!box) return;
        var field = editorActiveFieldId ? getFieldMeta(editorActiveFieldId) : null;
        if (!field) {
            box.innerHTML = '<div class="text-xs text-base-content/50 mb-1">当前字段</div><div class="font-medium">聚焦左侧字段后查看上下文</div>';
            return;
        }
        var before = field.context_before || '';
        var after = field.context_after || '';
        box.innerHTML = '<div class="flex items-center justify-between gap-2 mb-2">' +
            '<div><div class="text-xs text-base-content/50">当前字段</div><div class="font-medium">' +
            escapeHtml(field.label || field.key || '') + '</div></div>' +
            '<span class="badge badge-xs ' + fieldTypeBadgeClass(field) + '">' + getFieldTypeLabel(field.field_type) + '</span>' +
            '</div>' +
            '<div class="text-xs text-base-content/60 font-mono break-all">' + escapeHtml(field.key || '') + '</div>' +
            ((before || after) ? '<div class="mt-2 text-xs leading-relaxed"><span class="text-base-content/50">' +
            escapeHtml(before) + '</span><span class="text-error font-semibold">{ }</span><span class="text-base-content/50">' +
            escapeHtml(after) + '</span></div>' : '');
    }

    function syncActiveHighlights() {
        document.querySelectorAll('.field-item').forEach(function(item) {
            item.classList.toggle('editor-field-active', normalizeFieldId(item.id.replace('field_', '')) === editorActiveFieldId);
        });
        document.querySelectorAll('[data-preview-field]').forEach(function(el) {
            el.classList.toggle('active', normalizeFieldId(el.dataset.previewField) === editorActiveFieldId);
        });
        document.querySelectorAll('[data-structure-field]').forEach(function(el) {
            el.classList.toggle('active', normalizeFieldId(el.dataset.structureField) === editorActiveFieldId);
        });
    }

    function setActiveField(id) {
        editorActiveFieldId = normalizeFieldId(id);
        renderActiveFieldContext();
        syncActiveHighlights();
    }

    function focusField(id) {
        var item = getFieldItem(id);
        if (!item) return;
        setActiveField(id);
        item.scrollIntoView({ behavior: 'smooth', block: 'center' });
        var input = item.querySelector('input:not([type="hidden"]):not([readonly]), textarea, select');
        if (input) {
            setTimeout(function() { input.focus({ preventScroll: true }); }, 150);
        }
    }

    function setAssistTab(tabName) {
        document.querySelectorAll('.editor-assist-tab').forEach(function(btn) {
            var active = btn.dataset.assistTab === tabName;
            btn.classList.toggle('tab-active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
            btn.setAttribute('tabindex', active ? '0' : '-1');
        });
        document.querySelectorAll('.editor-assist-pane').forEach(function(pane) {
            pane.classList.toggle('hidden', pane.dataset.assistPane !== tabName);
        });
        if (tabName === 'review') renderMissingFieldList();
        if (tabName === 'structure') renderStructureList();
    }

    function bindAssistPanel() {
        document.querySelectorAll('.editor-assist-tab').forEach(function(btn) {
            btn.addEventListener('click', function() { setAssistTab(btn.dataset.assistTab || 'preview'); });
            btn.addEventListener('keydown', function(event) {
                var tabs = Array.from(document.querySelectorAll('.editor-assist-tab'));
                var index = tabs.indexOf(btn);
                var nextIndex = index;
                if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
                else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
                else if (event.key === 'Home') nextIndex = 0;
                else if (event.key === 'End') nextIndex = tabs.length - 1;
                else return;
                event.preventDefault();
                setAssistTab(tabs[nextIndex].dataset.assistTab || 'preview');
                tabs[nextIndex].focus();
            });
        });
        document.querySelectorAll('[data-assist-tab-jump]').forEach(function(btn) {
            btn.addEventListener('click', function() { setAssistTab(btn.dataset.assistTabJump || 'preview'); });
        });
        document.addEventListener('click', function(e) {
            var preview = e.target.closest('[data-preview-field]');
            if (preview) { focusField(preview.dataset.previewField); return; }
            var missing = e.target.closest('[data-missing-field]');
            if (missing) { focusField(missing.dataset.missingField); return; }
            var structure = e.target.closest('[data-structure-field]');
            if (structure) { focusField(structure.dataset.structureField); }
        });
        document.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            var preview = e.target.closest ? e.target.closest('[data-preview-field]') : null;
            if (!preview) return;
            e.preventDefault();
            focusField(preview.dataset.previewField);
        });
        document.addEventListener('focusin', function(e) {
            var item = e.target.closest ? e.target.closest('.field-item') : null;
            if (item) setActiveField(item.id.replace('field_', ''));
        });
        window.addEventListener('resize', fitContractPreviewPage);
    }

    function renderAssistPanel() {
        renderLivePreview();
        renderMissingFieldList();
        renderStructureList();
        renderActiveFieldContext();
        syncActiveHighlights();
    }

    function scheduleAssistRender() {
        if (assistRenderQueued) return;
        assistRenderQueued = true;
        var raf = window.requestAnimationFrame || function(fn) { return setTimeout(fn, 0); };
        raf(function() {
            assistRenderQueued = false;
            renderAssistPanel();
        });
    }

    // ── Progress ──
    function onFieldChange(id) {
        const item = document.getElementById('field_' + id);
        if (!item) return;
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
        setActiveField(id);
        updateProgress();
    }

    function updateProgress() {
        let filled = 0;
        document.querySelectorAll('.field-item').forEach(item => {
            if (item.classList.contains('field-calc')) return;
            if (item.querySelector('.table-editor')) {
                const tableFilled = tableFieldHasContent(item.id.replace('field_', ''));
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
        var progress = document.getElementById('editorProgress');
        var progressPercent = document.getElementById('progressPercent');
        if (progress) progress.setAttribute('aria-valuenow', String(pct));
        if (progressPercent) progressPercent.textContent = pct + '%';

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
        scheduleAssistRender();
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
            html += '<input type="text" class="th-input input input-ghost input-xs w-20 font-semibold" value="' + escapeHtml(col.label) + '" data-editor-action="column-label" data-field-id="' + fid + '" data-column-index="' + ci + '">';
            html += '<code class="var-code table-var-code badge badge-xs font-mono">' + escapeHtml(col.key || ('col_' + ci)) + '</code>';
            if (col.field_type === 'calculated') {
                html += ' <span class="calc-tag badge badge-warning badge-xs">自动</span>';
            }
            html += '<button type="button" class="th-del-btn btn btn-ghost btn-xs px-1 text-base-content/30 hover:text-error" data-editor-action="remove-column-at" data-field-id="' + fid + '" data-column-index="' + ci + '">&times;</button>';
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
        scheduleAssistRender();
        if (typeof scheduleDraftSave === 'function') scheduleDraftSave();
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
        actionTd.innerHTML = '<button type="button" class="btn btn-ghost btn-xs text-error" data-editor-action="remove-this-row"><i data-lucide="x" class="w-3 h-3"></i></button>';
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
        scheduleAssistRender();
        if (typeof scheduleDraftSave === 'function') scheduleDraftSave();
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
    var baseTriggerCalc = window.ContractFormulaEngine.triggerCalc;
    var baseRecalcField = window.ContractFormulaEngine.recalcField;
    var baseRecalcAllFields = window.ContractFormulaEngine.recalcAllFields;

    function triggerCalc(changedId) {
        if (typeof baseTriggerCalc === 'function') baseTriggerCalc(changedId);
        scheduleAssistRender();
    }

    function recalcField(el) {
        var result;
        if (typeof baseRecalcField === 'function') result = baseRecalcField(el);
        scheduleAssistRender();
        return result;
    }

    function recalcAllFields() {
        var result;
        if (typeof baseRecalcAllFields === 'function') result = baseRecalcAllFields();
        scheduleAssistRender();
        return result;
    }

    // ── Safe eval (from formula-engine.js) ──
    var safeEval = window.ContractFormulaEngine.safeEval;

    // ── Save defaults ──
    document.getElementById('saveDefaultsBtn').addEventListener('click', function() {
        var btn = this;
        var originalText = btn.innerHTML;
        Object.keys(columnsData).forEach(function(fid) {
            try { syncColumnsInput(parseInt(fid)); updateTableData(parseInt(fid)); } catch(e) {}
        });
        btn.disabled = true;
        btn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> 保存中…';
        window.ContractEditor.generation.saveDefaults(document.getElementById('editorForm'))
        .then(function(data) {
            if (window.ContractEditor.draft) window.ContractEditor.draft.markClean();
            showToast(data.message || '预制内容已保存', 'success');
        })
        .catch(function(err) { showToast(err.message || '保存失败', 'error'); console.error(err); })
        .finally(function() { btn.disabled = false; btn.innerHTML = originalText; });
    });

    var pendingPreflight = null;
    var preflightReturnFocus = null;

    function announceEditorStatus(message) {
        var status = document.getElementById('editorStatusLive');
        if (!status) return;
        status.textContent = '';
        window.setTimeout(function() { status.textContent = message; }, 20);
    }

    function generationActionUrl(isBatch, form) {
        return isBatch ? editorConfig.urls.generateBatch : form.action;
    }

    function runPreflight(form, isBatch) {
        return window.ContractEditor.generation.preflight(form, isBatch);
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
        var issueCount = document.getElementById('preflightIssueCount');
        var blocking = payload.blocking || [];
        var warnings = payload.warnings || [];

        summary.textContent = preflightSummary(payload);
        blockingList.innerHTML = listHtml(blocking);
        warningList.innerHTML = listHtml(warnings);
        blockingWrap.classList.toggle('hidden', blocking.length === 0);
        warningWrap.classList.toggle('hidden', warnings.length === 0);
        confirmBtn.classList.toggle('hidden', blocking.length > 0);
        issueCount.textContent = (blocking.length + warnings.length) + ' 项提醒';
        issueCount.classList.toggle('badge-error', blocking.length > 0);
        issueCount.classList.toggle('badge-warning', blocking.length === 0);
        setAssistTab('review');
        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        window.setTimeout(function() { panel.focus({ preventScroll: true }); }, 150);
        announceEditorStatus(blocking.length
            ? '生成前检查发现 ' + blocking.length + ' 项必须修正的问题。'
            : '生成前检查完成，有 ' + warnings.length + ' 项提醒，请确认。');
    }

    function setGenerating(btn, text) {
        btn.disabled = true;
        btn.setAttribute('aria-disabled', 'true');
        btn.innerHTML = text;
    }

    function resetGenerateButton(btn, origText) {
        btn.disabled = false;
        btn.removeAttribute('aria-disabled');
        btn.innerHTML = origText;
    }

    function performGeneration(form, actionUrl, btn, origText, overlay) {
        Object.keys(columnsData).forEach(function(fid) {
            try { syncColumnsInput(parseInt(fid)); } catch(e) {}
        });
        var formData = new FormData(form);
        setGenerating(btn, '<span class="loading loading-spinner"></span> 生成中…');
        overlay.classList.add('active');
        document.getElementById('editorForm').setAttribute('aria-busy', 'true');
        announceEditorStatus('正在生成合同文档。');

        window.ContractEditor.generation.generate(actionUrl, formData)
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
            var genErrors = response.headers.get('X-Generation-Errors') || '';
            var ledgerError = response.headers.get('X-Ledger-Error') || '';
            try { genErrors = decodeURIComponent(genErrors); } catch(e) {}
            try { ledgerError = decodeURIComponent(ledgerError); } catch(e) {}
            var filename = isZip ? '批量合同.zip' : '合同.docx';
            var match = disposition.match(/filename\*?=(?:UTF-8'')?([^;\s"']+)/i);
            if (match) { try { filename = decodeURIComponent(match[1]); } catch(e) {} }
            return response.blob().then(function(blob) {
                return { blob: blob, filename: filename, detailUrl: detailUrl,
                         isBatch: isZip, genErrors: genErrors, ledgerError: ledgerError };
            });
        })
        .then(function(result) {
            var url = window.URL.createObjectURL(result.blob);
            var a = document.createElement('a');
            a.href = url; a.download = result.filename;
            document.body.appendChild(a); a.click(); a.remove();
            overlay.classList.remove('active');
            document.getElementById('editorForm').removeAttribute('aria-busy');
            resetGenerateButton(btn, origText);
            if (result.genErrors) {
                showToast('部分合同生成出错：' + result.genErrors, 'error');
            } else if (result.ledgerError) {
                showToast(result.ledgerError, 'error');
            } else {
                showToast(result.isBatch ? '批量合同已生成' : '合同已生成', 'success');
            }
            showGenerationResult(result, url);
            announceEditorStatus(result.isBatch ? '批量合同已生成并开始下载。' : '合同已生成并开始下载。');
        })
        .catch(function(err) {
            overlay.classList.remove('active');
            document.getElementById('editorForm').removeAttribute('aria-busy');
            resetGenerateButton(btn, origText);
            showToast(err.message || '生成失败', 'error');
            announceEditorStatus('生成失败：' + (err.message || '未知错误'));
            console.error(err);
        });
    }

    // ── Form submit ──
    document.getElementById('editorForm').addEventListener('submit', function(e) {
        e.preventDefault();
        var overlay = document.getElementById('loadingOverlay');
        var btn = document.getElementById('generateBtn');
        var origText = btn.innerHTML;
        preflightReturnFocus = document.activeElement;

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
                if (!tableFieldHasContent(item.id.replace('field_', ''))) {
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
            setAssistTab('review');
            renderMissingFieldList();
            if (firstRequired) focusField(firstRequired.id.replace('field_', ''));
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
        if (preflightReturnFocus && typeof preflightReturnFocus.focus === 'function') {
            preflightReturnFocus.focus();
        }
        announceEditorStatus('已返回合同填写。');
    });

    document.getElementById('preflightPanel').addEventListener('keydown', function(event) {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        document.getElementById('preflightCloseBtn').click();
    });

    function showGenerationResult(result, blobUrl) {
        if (currentGeneratedUrl) {
            window.URL.revokeObjectURL(currentGeneratedUrl);
        }
        currentGeneratedUrl = blobUrl;

        // 清除草稿（生成成功后无需保留）
        if (window.ContractEditor.draft) {
            window.ContractEditor.draft.clear();
        }

        const panel = document.getElementById('generationResultPanel');
        const downloadLink = document.getElementById('resultDownloadLink');
        const detailLink = document.getElementById('resultDetailLink');
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

        setAssistTab('review');
        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // icons.js observes dynamic nodes and renders icons automatically.
    }

    document.getElementById('resultContinueBtn').addEventListener('click', function() {
        document.getElementById('generationResultPanel').classList.add('hidden');
    });

    window.ContractEditor.core = Object.freeze({
        onFieldChange,
        updateProgress,
        bindEditorFilters,
        setEditorFilter,
        bindAssistPanel,
        setAssistTab,
        renderLivePreview,
        renderMissingFieldList,
        focusField,
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
