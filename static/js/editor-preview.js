/** Preview module facade and preview-button binding. */
'use strict';

(function registerPreviewModule(editor) {
  function submitPreview() {
    if (!editor.config.templateFilename || editor.config.templateFilename === 'None') {
      showToast('请先保存模板后再预览', 'error');
      return;
    }
    var form = document.getElementById('editorForm');
    var originalAction = form.action;
    var originalTarget = form.target;
    form.action = editor.config.urls.preview;
    form.target = '_blank';
    form.submit();
    form.action = originalAction;
    form.target = originalTarget;
  }

  document.addEventListener('click', function(event) {
    if (event.target.closest('[data-editor-action="preview"]')) submitPreview();
  });

  editor.preview = Object.freeze({
    render: renderLivePreview,
    renderMissing: renderMissingFieldList,
    focusField: focusField,
    submit: submitPreview,
  });
})(window.ContractEditor);
