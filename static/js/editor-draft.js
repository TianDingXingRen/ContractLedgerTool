/** Local editor draft persistence. */
'use strict';

var draftKey = 'ct_draft_' + (editorConfig.templateFilename || 'unknown');
var draftTimer;
var draftDirty = false;
var draftRestoring = false;

function saveDraft() {
  try {
    var data = {};
    document.querySelectorAll('.field-item').forEach(function(item) {
      if (item.classList.contains('field-calc')) return;
      var input = item.querySelector('.field-input, .field-select, textarea');
      var key = item.dataset.fieldKey;
      if (input && key) data[key] = input.value;
    });
    Object.keys(columnsData).forEach(function(fid) {
      var dataElement = document.getElementById('table_data_' + fid);
      var columnsElement = document.getElementById('table_cols_input_' + fid);
      if (dataElement) data['_table_' + fid] = dataElement.value;
      if (columnsElement) data['_table_cols_' + fid] = columnsElement.value;
    });
    [['projectName', '_project_name'], ['coverageStart', '_coverage_start'],
      ['coverageEnd', '_coverage_end']].forEach(function(pair) {
      var element = document.getElementById(pair[0]);
      if (element) data[pair[1]] = element.value;
    });
    data._saved_at = new Date().toISOString();
    localStorage.setItem(draftKey, JSON.stringify(data));
  } catch (error) {
    console.warn('保存本地草稿失败', error);
  }
}

function restoreDraft() {
  try {
    var raw = localStorage.getItem(draftKey);
    if (!raw) return;
    var data = JSON.parse(raw);
    if (!data || !data._saved_at) return;
    if ((Date.now() - new Date(data._saved_at).getTime()) / 3600000 > 72) {
      localStorage.removeItem(draftKey);
      return;
    }
    var hasContent = false;
    document.querySelectorAll('.field-item').forEach(function(item) {
      if (item.classList.contains('field-calc')) return;
      var input = item.querySelector('.field-input, .field-select, textarea');
      var key = item.dataset.fieldKey;
      if (input && key && data[key] !== undefined) {
        input.value = data[key];
        if (data[key] !== '') hasContent = true;
      }
    });
    Object.keys(columnsData).forEach(function(fid) {
      var storedColumns = data['_table_cols_' + fid];
      if (storedColumns) {
        document.getElementById('table_cols_input_' + fid).value = storedColumns;
        columnsData[fid] = JSON.parse(storedColumns);
        renderTableHeader(parseInt(fid, 10));
      }
      var tableRaw = data['_table_' + fid] || data['_table_data_' + fid];
      if (!tableRaw) return;
      document.getElementById('table_data_' + fid).value = tableRaw;
      var rows = JSON.parse(tableRaw || '[]');
      var body = document.getElementById('table_body_' + fid);
      if (body && Array.isArray(rows) && rows.length) {
        body.replaceChildren();
        rows.forEach(function(row) { addTableRow(parseInt(fid, 10), row); });
        renumberRows(parseInt(fid, 10));
        updateTableData(parseInt(fid, 10));
        hasContent = true;
      }
    });
    [['projectName', '_project_name'], ['coverageStart', '_coverage_start'],
      ['coverageEnd', '_coverage_end']].forEach(function(pair) {
      var element = document.getElementById(pair[0]);
      if (element && data[pair[1]] !== undefined) element.value = data[pair[1]];
    });
    if (hasContent) {
      updateProgress();
      recalcAllFields();
    }
  } catch (error) {
    console.warn('恢复本地草稿失败', error);
  }
}

function scheduleDraftSave() {
  if (draftRestoring) return;
  draftDirty = true;
  clearTimeout(draftTimer);
  draftTimer = setTimeout(function() {
    saveDraft();
    draftDirty = false;
  }, 5000);
}

function bindDraftAutoSave() {
  var form = document.getElementById('editorForm');
  if (!form || form.dataset.draftBound === '1') return;
  form.dataset.draftBound = '1';
  form.addEventListener('input', scheduleDraftSave);
  form.addEventListener('change', scheduleDraftSave);
}

function clearDraft() {
  clearTimeout(draftTimer);
  draftDirty = false;
  localStorage.removeItem(draftKey);
}

setInterval(function() {
  if (draftDirty) {
    saveDraft();
    draftDirty = false;
  }
}, 30000);
window.addEventListener('beforeunload', function() {
  if (draftDirty) saveDraft();
});

window.ContractEditor.draft = Object.freeze({
  save: saveDraft,
  restore: restoreDraft,
  schedule: scheduleDraftSave,
  clear: clearDraft,
});
