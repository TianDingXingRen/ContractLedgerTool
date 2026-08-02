/** Editor orchestration and keyboard navigation. */
'use strict';

document.addEventListener('DOMContentLoaded', function() {
  fields.filter(function(field) { return field.field_type === 'table'; }).forEach(function(field) {
    initTable(field.id);
  });
  recalcAllFields();
  updateProgress();
  bindEditorFilters();
  bindAssistPanel();
  setEditorFilter('all');
  draftRestoring = true;
  restoreDraft();
  draftRestoring = false;
  bindDraftAutoSave();
});

document.addEventListener('keydown', function(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault();
    document.getElementById('saveDefaultsBtn').click();
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    document.getElementById('generateBtn').click();
    return;
  }
  if (event.key === 'Escape') {
    var panel = document.getElementById('generationResultPanel');
    if (panel && !panel.classList.contains('hidden')) {
      panel.classList.add('hidden');
      event.preventDefault();
    }
  }
});
