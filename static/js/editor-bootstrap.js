/** Editor orchestration and keyboard navigation. */
'use strict';

document.addEventListener('DOMContentLoaded', function() {
  draftRestoring = true;
  try {
    fields.filter(function(field) { return field.field_type === 'table'; }).forEach(function(field) {
      initTable(field.id);
    });
    recalcAllFields();
    updateProgress();
    bindEditorFilters();
    bindAssistPanel();
    setEditorFilter('all');
    restoreDraft();
  } finally {
    // Table construction calls updateTableData(), so the restoring guard must
    // cover initialization as well as loading a saved draft.
    draftRestoring = false;
  }
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
