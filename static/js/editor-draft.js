/** Local editor draft persistence. */
'use strict';

function buildDraftTemplateSchema(config) {
  return JSON.stringify((config.fields || []).map(function(field) {
    return {
      id: String(field.id == null ? '' : field.id),
      key: String(field.key || ''),
      type: String(field.field_type || ''),
      formula: String(field.formula || ''),
      decimals: field.decimal_places == null ? null : Number(field.decimal_places),
      columns: (field.columns || []).map(function(column) {
        return {
          key: String(column.key || ''),
          type: String(column.field_type || ''),
          formula: String(column.formula || ''),
          decimals: column.decimal_places == null ? null : Number(column.decimal_places),
        };
      }),
    };
  }));
}

function draftSchemaHash(schema) {
  var hash = 2166136261;
  for (var index = 0; index < schema.length; index++) {
    hash ^= schema.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

var draftTemplateSchema = buildDraftTemplateSchema(editorConfig);
var legacyDraftKey = 'ct_draft_' + (editorConfig.templateFilename || 'unknown');
var legacySchemaDraftKey = 'ct_draft_v2_' +
  (editorConfig.templateFilename || 'unknown') + '_' +
  draftSchemaHash(draftTemplateSchema);
var draftTemplateRevision = String(
  editorConfig.templateRevision || draftSchemaHash(draftTemplateSchema)
);
var draftScope = String(editorConfig.draftScope || 'template::');
var draftIdentityHash = draftSchemaHash([
  draftTemplateRevision,
  draftScope,
  draftTemplateSchema,
].join('\u001f'));
var draftKey = 'ct_draft_v3_' + (editorConfig.templateFilename || 'unknown') + '_' +
  draftIdentityHash;
var draftTimer;
var draftDirty = false;
var draftRestoring = false;
var hasUnsavedChanges = false;

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
    var coverageMode = document.querySelector('input[name="coverage_mode"]:checked');
    data._coverage_mode = coverageMode ? coverageMode.value : '';
    data._template_schema = draftTemplateSchema;
    data._template_revision = draftTemplateRevision;
    data._draft_scope = draftScope;
    data._saved_at = new Date().toISOString();
    localStorage.setItem(draftKey, JSON.stringify(data));
  } catch (error) {
    console.warn('保存本地草稿失败', error);
  }
}

function validDraftColumns(columns) {
  if (!Array.isArray(columns)) return false;
  var keys = {};
  return columns.every(function(column) {
    if (!column || typeof column !== 'object' || Array.isArray(column)) return false;
    var key = String(column.key || '');
    if (!key || keys[key]) return false;
    keys[key] = true;
    return true;
  });
}

function parseDraftTables(data) {
  var parsed = {};
  var fieldIds = Object.keys(columnsData);
  for (var index = 0; index < fieldIds.length; index++) {
    var fid = fieldIds[index];
    var columnsRaw = data['_table_cols_' + fid];
    var tableRaw = data['_table_' + fid] || data['_table_data_' + fid];
    if (columnsRaw === undefined && tableRaw === undefined) continue;
    try {
      var storedColumns = columnsRaw ? JSON.parse(columnsRaw) : columnsData[fid];
      var rows = tableRaw ? JSON.parse(tableRaw) : [];
      if (!validDraftColumns(storedColumns) || !Array.isArray(rows)) return null;
      var allowedKeys = {};
      storedColumns.forEach(function(column) { allowedKeys[column.key] = true; });
      var validRows = rows.every(function(row) {
        return row && typeof row === 'object' && !Array.isArray(row) &&
          Object.keys(row).every(function(key) { return allowedKeys[key]; });
      });
      if (!validRows) return null;
      parsed[fid] = { columns: storedColumns, rows: rows };
    } catch (error) {
      return null;
    }
  }
  return parsed;
}

function restoreDraft() {
  var previousRestoring = draftRestoring;
  draftRestoring = true;
  try {
    var raw = localStorage.getItem(draftKey);
    if (!raw) return false;
    var data = JSON.parse(raw);
    if (!data || !data._saved_at ||
        data._template_schema !== draftTemplateSchema ||
        data._template_revision !== draftTemplateRevision ||
        data._draft_scope !== draftScope) return false;
    if ((Date.now() - new Date(data._saved_at).getTime()) / 3600000 > 72) {
      localStorage.removeItem(draftKey);
      return false;
    }
    var parsedTables = parseDraftTables(data);
    if (!parsedTables) {
      console.warn('本地草稿结构与当前模板不兼容，已忽略');
      return false;
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
      var storedTable = parsedTables[fid];
      if (!storedTable) return;
      if (storedTable.columns) {
        var storedColumns = JSON.stringify(storedTable.columns);
        document.getElementById('table_cols_input_' + fid).value = storedColumns;
        columnsData[fid] = storedTable.columns;
        renderTableHeader(parseInt(fid, 10));
      }
      var tableRaw = JSON.stringify(storedTable.rows);
      document.getElementById('table_data_' + fid).value = tableRaw;
      var rows = storedTable.rows;
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
    if (data._coverage_mode !== undefined) {
      var coverageMode = Array.from(
        document.querySelectorAll('input[name="coverage_mode"]')
      ).find(function(element) { return element.value === data._coverage_mode; });
      if (coverageMode) coverageMode.checked = true;
    }
    if (window.CoverageMode) window.CoverageMode.syncAll(document);
    if (hasContent) {
      hasUnsavedChanges = true;
      updateProgress();
      recalcAllFields();
    }
    return hasContent;
  } catch (error) {
    console.warn('恢复本地草稿失败', error);
    return false;
  } finally {
    draftRestoring = previousRestoring;
  }
}

function scheduleDraftSave() {
  if (draftRestoring) return;
  draftDirty = true;
  hasUnsavedChanges = true;
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
  hasUnsavedChanges = false;
  localStorage.removeItem(draftKey);
  localStorage.removeItem(legacyDraftKey);
  localStorage.removeItem(legacySchemaDraftKey);
}

function preserveDraft() {
  clearTimeout(draftTimer);
  saveDraft();
  draftDirty = false;
  hasUnsavedChanges = true;
}

function markClean() {
  clearTimeout(draftTimer);
  if (draftDirty) saveDraft();
  draftDirty = false;
  hasUnsavedChanges = false;
}

setInterval(function() {
  if (draftDirty) {
    saveDraft();
    draftDirty = false;
  }
}, 30000);
window.addEventListener('beforeunload', function(event) {
  if (draftDirty) saveDraft();
  if (!hasUnsavedChanges) return;
  event.preventDefault();
  event.returnValue = '';
});

window.ContractEditor.draft = Object.freeze({
  save: saveDraft,
  restore: restoreDraft,
  schedule: scheduleDraftSave,
  clear: clearDraft,
  preserve: preserveDraft,
  markClean: markClean,
  hasUnsavedChanges: function() { return hasUnsavedChanges; },
});
