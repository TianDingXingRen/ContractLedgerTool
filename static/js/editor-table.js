/** Delegated editor field and table events (CSP-safe, no inline handlers). */
'use strict';

(function bindEditorTableEvents(editor) {
  function fieldIdFrom(element) {
    var item = element.closest('.field-item');
    return item ? item.id.replace('field_', '') : '';
  }

  function updateField(event) {
    var target = event.target;
    if (!target.closest || !target.closest('.field-item')) return;
    if (target.classList.contains('table-cell-input') || target.classList.contains('th-input')) return;
    var fieldId = fieldIdFrom(target);
    if (!fieldId) return;
    onFieldChange(fieldId);
    triggerCalc(fieldId);
  }

  document.addEventListener('input', updateField);
  document.addEventListener('change', function(event) {
    var action = event.target.dataset.editorAction;
    if (action === 'column-label') {
      updateColumnLabel(Number(event.target.dataset.fieldId), Number(event.target.dataset.columnIndex), event.target.value);
      return;
    }
    updateField(event);
  });

  document.addEventListener('click', function(event) {
    var button = event.target.closest('[data-editor-action]');
    if (!button) return;
    var fieldId = Number(button.dataset.fieldId);
    var actions = {
      'add-row': function() { addTableRow(fieldId); },
      'remove-row': function() { removeTableRow(fieldId); },
      'add-column': function() { addTableColumn(fieldId); },
      'remove-column': function() { removeTableColumn(fieldId); },
      'remove-column-at': function() { removeTableColumnAt(fieldId, Number(button.dataset.columnIndex)); },
      'remove-this-row': function() { removeThisRow(button); },
    };
    if (actions[button.dataset.editorAction]) actions[button.dataset.editorAction]();
  });

  editor.table = Object.freeze({
    init: initTable,
    addRow: addTableRow,
    addColumn: addTableColumn,
    removeRow: removeTableRow,
    removeColumn: removeTableColumn,
  });
})(window.ContractEditor);
