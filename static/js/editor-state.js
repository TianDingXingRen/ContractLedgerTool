/** Editor boot configuration and shared page state. */
'use strict';

var editorConfigElement = document.getElementById('contractEditorConfig');
if (!editorConfigElement) throw new Error('缺少合同编辑器启动配置');

var editorConfig = JSON.parse(editorConfigElement.textContent || '{}');
var fields = Array.isArray(editorConfig.fields) ? editorConfig.fields : [];
var totalFields = Number(editorConfig.fieldCount || fields.length || 0);
var filledCount = document.getElementById('filledCount');
var progressFill = document.getElementById('progressFill');
var columnsData = {};
var currentGeneratedUrl = '';
var escapeHtml = window.ContractToolApi.escapeHtml;

window.ContractEditor = window.ContractEditor || {};
window.ContractEditor.config = Object.freeze(editorConfig);
window.ContractEditor.state = {
  fields: fields,
  columns: columnsData,
};
