// Shared shell behavior: theme, feedback, and form confirmations.

(function themeSystem() {
  'use strict';

  const storageKey = 'theme';

  function normalizeTheme(value) {
    return value === 'dark' ? 'dark' : 'light';
  }

  function readSavedTheme() {
    try {
      return normalizeTheme(window.localStorage.getItem(storageKey));
    } catch (_error) {
      return 'light';
    }
  }

  function replaceThemeIcon(button, theme) {
    const current = button.querySelector('[data-theme-icon]');
    const icon = document.createElement('i');
    icon.setAttribute('data-theme-icon', '');
    icon.setAttribute('data-lucide', theme === 'dark' ? 'sun' : 'moon');
    icon.style.width = '15px';
    icon.style.height = '15px';
    if (current) current.replaceWith(icon);
    else button.appendChild(icon);
  }

  function syncThemeButton(button, theme, replaceIcon) {
    if (!button) return;
    const dark = theme === 'dark';
    button.setAttribute('aria-pressed', dark ? 'true' : 'false');
    button.setAttribute('aria-label', dark ? '切换亮色模式' : '切换暗色模式');
    button.setAttribute('title', dark ? '切换亮色模式' : '切换暗色模式');
    const icon = button.querySelector('[data-theme-icon]');
    const expected = dark ? 'sun' : 'moon';
    if (replaceIcon && (!icon || icon.getAttribute('data-lucide') !== expected)) {
      replaceThemeIcon(button, theme);
    } else if (icon) {
      icon.setAttribute('data-lucide', expected);
    }
  }

  function applyTheme(theme, persist) {
    const normalized = normalizeTheme(theme);
    document.documentElement.dataset.theme = normalized;
    if (persist) {
      try {
        window.localStorage.setItem(storageKey, normalized);
      } catch (_error) {
        // The current page still switches theme when storage is unavailable.
      }
    }
    syncThemeButton(
      document.querySelector('[data-shell-action="toggle-theme"]'),
      normalized,
      persist
    );
    return normalized;
  }

  applyTheme(readSavedTheme(), false);

  document.addEventListener('DOMContentLoaded', () => {
    syncThemeButton(
      document.querySelector('[data-shell-action="toggle-theme"]'),
      normalizeTheme(document.documentElement.dataset.theme),
      true
    );
  });

  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-shell-action="toggle-theme"]');
    if (!toggle) return;
    const current = normalizeTheme(document.documentElement.dataset.theme);
    applyTheme(current === 'dark' ? 'light' : 'dark', true);
  });
})();

function toastCenter() {
  return {
    toasts: [],
    addToast(toast) {
      this.toasts.push(toast);
      const message = toast && (toast.msg || toast.message) ? (toast.msg || toast.message) : toast;
      const type = toast && toast.type ? toast.type : 'success';
      if (window.showToast) window.showToast(message, type);
      setTimeout(() => this.toasts.shift(), 3500);
    },
  };
}

(function feedbackSystem() {
  const TYPE_META = {
    success: { title: '操作成功', icon: 'check-circle' },
    error: { title: '操作失败', icon: 'x-circle' },
    warning: { title: '请确认', icon: 'alert-triangle' },
    info: { title: '提示', icon: 'info' },
  };

  function safeType(type) {
    return TYPE_META[type] ? type : 'success';
  }

  function renderIcons(root) {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons({ attrs: { 'stroke-width': 1.8 }, nameAttr: 'data-lucide' });
    }
  }

  function ensureToastStack() {
    let stack = document.getElementById('feedbackToastStack');
    if (stack) return stack;
    stack = document.createElement('div');
    stack.id = 'feedbackToastStack';
    stack.className = 'feedback-toast-stack';
    stack.setAttribute('aria-live', 'polite');
    stack.setAttribute('aria-atomic', 'false');
    document.body.appendChild(stack);
    return stack;
  }

  function showToast(message, type, options) {
    if (typeof type === 'object' && type !== null) {
      options = type;
      type = options.type;
    }
    const toastType = safeType(type || 'success');
    const meta = TYPE_META[toastType];
    const opts = options || {};
    const stack = ensureToastStack();
    const toast = document.createElement('div');
    toast.className = 'feedback-toast ' + toastType;
    toast.setAttribute('role', toastType === 'error' ? 'alert' : 'status');

    const icon = document.createElement('i');
    icon.setAttribute('data-lucide', opts.icon || meta.icon);
    icon.className = 'feedback-toast-icon';

    const textWrap = document.createElement('div');
    textWrap.className = 'feedback-toast-text';
    const title = document.createElement('div');
    title.className = 'feedback-toast-title';
    title.textContent = opts.title || meta.title;
    const body = document.createElement('div');
    body.className = 'feedback-toast-body';
    body.textContent = String(message || '');
    textWrap.appendChild(title);
    textWrap.appendChild(body);

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'feedback-toast-close';
    close.setAttribute('aria-label', '关闭提示');
    close.innerHTML = '<i data-lucide="x"></i>';

    toast.appendChild(icon);
    toast.appendChild(textWrap);
    toast.appendChild(close);
    stack.appendChild(toast);
    renderIcons(toast);

    const dismiss = () => {
      toast.classList.remove('show');
      window.setTimeout(() => toast.remove(), 220);
    };
    close.addEventListener('click', dismiss);
    window.requestAnimationFrame(() => toast.classList.add('show'));
    const duration = Number(opts.duration || (String(message || '').length > 90 ? 6200 : 3600));
    if (duration > 0) window.setTimeout(dismiss, duration);
  }

  function ensureDialog() {
    let backdrop = document.getElementById('feedbackDialogBackdrop');
    if (backdrop) return backdrop;
    backdrop = document.createElement('div');
    backdrop.id = 'feedbackDialogBackdrop';
    backdrop.className = 'feedback-dialog-backdrop';
    backdrop.innerHTML = [
      '<div class="feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="feedbackDialogTitle">',
      '  <div class="feedback-dialog-head">',
      '    <span class="feedback-dialog-icon"><i data-lucide="info"></i></span>',
      '    <div>',
      '      <div class="feedback-dialog-title" id="feedbackDialogTitle"></div>',
      '      <div class="feedback-dialog-message" id="feedbackDialogMessage"></div>',
      '    </div>',
      '  </div>',
      '  <div class="feedback-dialog-actions">',
      '    <button type="button" class="apple-btn apple-btn-ghost" data-feedback-cancel>取消</button>',
      '    <button type="button" class="apple-btn apple-btn-primary" data-feedback-confirm>确认</button>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(backdrop);
    return backdrop;
  }

  function openFeedbackDialog(config) {
    const cfg = config || {};
    const type = safeType(cfg.type || 'warning');
    const meta = TYPE_META[type];
    const backdrop = ensureDialog();
    const dialog = backdrop.querySelector('.feedback-dialog');
    const icon = backdrop.querySelector('.feedback-dialog-icon i');
    const title = backdrop.querySelector('#feedbackDialogTitle');
    const message = backdrop.querySelector('#feedbackDialogMessage');
    const confirmBtn = backdrop.querySelector('[data-feedback-confirm]');
    const cancelBtn = backdrop.querySelector('[data-feedback-cancel]');

    backdrop.className = 'feedback-dialog-backdrop ' + type;
    icon.setAttribute('data-lucide', cfg.icon || meta.icon);
    title.textContent = cfg.title || meta.title;
    message.textContent = String(cfg.message || '');
    confirmBtn.textContent = cfg.confirmText || '确认';
    cancelBtn.textContent = cfg.cancelText || '取消';
    cancelBtn.style.display = cfg.hideCancel ? 'none' : '';
    confirmBtn.classList.toggle('feedback-danger', !!cfg.danger || type === 'error');
    renderIcons(backdrop);

    return new Promise((resolve) => {
      let done = false;
      const previousActive = document.activeElement;

      function close(value) {
        if (done) return;
        done = true;
        backdrop.classList.remove('open');
        document.removeEventListener('keydown', onKey);
        confirmBtn.removeEventListener('click', onConfirm);
        cancelBtn.removeEventListener('click', onCancel);
        backdrop.removeEventListener('click', onBackdrop);
        if (previousActive && typeof previousActive.focus === 'function') {
          window.setTimeout(() => previousActive.focus(), 0);
        }
        resolve(value);
      }

      function onConfirm() { close(true); }
      function onCancel() { close(false); }
      function onBackdrop(event) {
        if (event.target === backdrop && !cfg.hideCancel) close(false);
      }
      function onKey(event) {
        if (event.key === 'Escape' && !cfg.hideCancel) close(false);
        if (event.key === 'Enter') close(true);
      }

      confirmBtn.addEventListener('click', onConfirm);
      cancelBtn.addEventListener('click', onCancel);
      backdrop.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onKey);
      backdrop.classList.add('open');
      window.setTimeout(() => confirmBtn.focus(), 0);
    });
  }

  function confirmAction(message, options) {
    const opts = options || {};
    return openFeedbackDialog({
      type: opts.type || 'warning',
      title: opts.title || '确认操作',
      message,
      confirmText: opts.confirmText || '确认',
      cancelText: opts.cancelText || '取消',
      danger: !!opts.danger,
    });
  }

  function showNotice(title, message, options) {
    const opts = options || {};
    return openFeedbackDialog({
      type: opts.type || 'info',
      title: title || '提示',
      message,
      confirmText: opts.confirmText || '知道了',
      hideCancel: true,
    });
  }

  function formConfirmOptions(form) {
    return {
      title: form.dataset.confirmTitle || '确认操作',
      confirmText: form.dataset.confirmOk || '确认',
      cancelText: form.dataset.confirmCancel || '取消',
      danger: form.dataset.confirmDanger === 'true',
      type: form.dataset.confirmType || 'warning',
    };
  }

  document.addEventListener('submit', (event) => {
    const form = event.target.closest ? event.target.closest('form[data-confirm]') : null;
    if (!form || form.dataset.confirmed === '1') return;
    event.preventDefault();
    event.stopPropagation();
    confirmAction(form.dataset.confirm, formConfirmOptions(form)).then((ok) => {
      if (!ok) return;
      form.dataset.confirmed = '1';
      if (typeof form.requestSubmit === 'function') form.requestSubmit();
      else form.submit();
      window.setTimeout(() => { delete form.dataset.confirmed; }, 0);
    });
  }, true);

  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-shell-action="toggle-sidebar"]');
    if (!toggle) return;
    const sidebar = document.getElementById('sp');
    if (sidebar) sidebar.classList.toggle('open');
  });

  document.addEventListener('change', (event) => {
    const input = event.target.closest
      ? event.target.closest('[data-file-picker] input[type="file"]')
      : null;
    if (!input) return;
    const picker = input.closest('[data-file-picker]');
    const name = picker ? picker.querySelector('[data-file-name]') : null;
    if (!name) return;
    name.textContent = input.files && input.files.length
      ? input.files[0].name
      : '未选择文件';
  });

  window.showToast = showToast;
  window.confirmAction = confirmAction;
  window.showNotice = showNotice;
  document.documentElement.dataset.appShell = 'ready';
})();
