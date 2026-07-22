/** Shared native-dialog drawer behavior. */
'use strict';

(function uiDrawerController() {
  const openerByDialog = new WeakMap();
  const snapshotByForm = new WeakMap();

  function formSnapshot(form) {
    return Array.from(new FormData(form).entries())
      .map(function(entry) { return entry[0] + '=' + entry[1]; })
      .sort()
      .join('&');
  }

  function rememberForms(dialog) {
    dialog.querySelectorAll('form').forEach(function(form) {
      snapshotByForm.set(form, formSnapshot(form));
    });
  }

  function isDirty(dialog) {
    return Array.from(dialog.querySelectorAll('form')).some(function(form) {
      return snapshotByForm.has(form) && snapshotByForm.get(form) !== formSnapshot(form);
    });
  }

  function finishClose(dialog) {
    dialog.classList.remove('is-closing');
    dialog.close();
    const opener = openerByDialog.get(dialog);
    if (opener && document.contains(opener)) opener.focus();
  }

  async function requestClose(dialog, force) {
    if (!force && isDirty(dialog) && window.confirmAction) {
      const confirmed = await window.confirmAction('当前修改尚未保存，确定关闭吗？', {
        title: '放弃修改', confirmText: '放弃修改', danger: true,
      });
      if (!confirmed) return;
    }
    dialog.classList.add('is-closing');
    window.setTimeout(function() { finishClose(dialog); }, 160);
  }

  document.addEventListener('click', function(event) {
    const opener = event.target.closest('[data-drawer-open]');
    if (opener) {
      const dialog = document.getElementById(opener.dataset.drawerOpen);
      if (!dialog || typeof dialog.showModal !== 'function') return;
      openerByDialog.set(dialog, opener);
      rememberForms(dialog);
      dialog.showModal();
      const focusTarget = dialog.querySelector('[autofocus], input:not([type="hidden"]), select, textarea, button');
      if (focusTarget) window.setTimeout(function() { focusTarget.focus(); }, 0);
      return;
    }
    const closer = event.target.closest('[data-drawer-close]');
    if (closer) {
      const dialog = closer.closest('dialog');
      if (dialog) requestClose(dialog, false);
      return;
    }
    if (event.target instanceof HTMLDialogElement && event.target.classList.contains('ui-drawer')) {
      requestClose(event.target, false);
    }
  });

  document.addEventListener('cancel', function(event) {
    if (!event.target.classList.contains('ui-drawer')) return;
    event.preventDefault();
    requestClose(event.target, false);
  });

  document.addEventListener('submit', function(event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.closest('.ui-drawer')) return;
    form.dataset.submitting = 'true';
    form.querySelectorAll('button[type="submit"]').forEach(function(button) {
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      button.textContent = '正在保存…';
    });
  });
})();
