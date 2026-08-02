/** Diagnostics page refresh, copy, and folder actions. */
'use strict';

document.addEventListener('DOMContentLoaded', function() {
  const payloadElement = document.getElementById('diagnosticsPayload');
  let payload = JSON.parse(payloadElement.textContent || '{}');
  const apiUrl = payloadElement.dataset.apiUrl;
  const toast = document.getElementById('diagnosticsToast');

  function showMessage(message, type) {
    toast.textContent = message;
    toast.className = 'alert mb-3 text-sm ' + (type === 'error' ? 'alert-error' : 'alert-success');
    toast.classList.remove('hidden');
    window.setTimeout(function() { toast.classList.add('hidden'); }, 2600);
  }

  function applyDiagnostics(data) {
    payload = data;
    const autostart = data.autostart || {};
    const badge = document.getElementById('autostartDiagnosticBadge');
    badge.textContent = autostart.enabled ? '已开启' : '未开启';
    badge.classList.toggle('badge-success', !!autostart.enabled);
    badge.classList.toggle('badge-ghost', !autostart.enabled);
    document.getElementById('autostartDiagnosticDescription').textContent = autostart.description || '-';
    document.getElementById('autostartTaskState').textContent = autostart.task_state || '-';
    ['templates', 'contracts', 'backups'].forEach(function(key) {
      const target = document.querySelector('[data-diagnostics-field="' + key + '"]');
      if (target && data.counts) target.textContent = data.counts[key];
    });
    const integrity = data.generation_integrity || {};
    const integrityFields = {
      'generation-unfinished': 'unfinished',
      'generation-attention': 'attention',
      'generation-recovered': 'recovered',
      'generation-missing': 'missing_documents',
      'generation-staging': 'staging_files'
    };
    Object.keys(integrityFields).forEach(function(field) {
      const target = document.querySelector('[data-diagnostics-field="' + field + '"]');
      if (target) target.textContent = integrity[integrityFields[field]] || 0;
    });
    const integrityBadge = document.getElementById('generationIntegrityBadge');
    if (integrityBadge) {
      integrityBadge.textContent = integrity.ok ? '正常' : '需检查';
      integrityBadge.classList.toggle('badge-success', !!integrity.ok);
      integrityBadge.classList.toggle('badge-warning', !integrity.ok);
    }
  }

  function refreshDiagnostics(label) {
    return window.ContractToolApi.requestJson(apiUrl, {headers: {'Accept': 'application/json'}})
      .then(function(data) {
        applyDiagnostics(data);
        if (label) showMessage(label, 'success');
        return data;
      }).catch(function(error) { showMessage(error.message || '检测失败', 'error'); });
  }

  document.getElementById('copyDiagnosticsBtn').addEventListener('click', function() {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      showMessage('当前浏览器不支持自动复制', 'error');
      return;
    }
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
      .then(function() { showMessage('诊断信息已复制', 'success'); })
      .catch(function() { showMessage('复制失败，请使用浏览器手动复制页面内容', 'error'); });
  });
  document.getElementById('refreshDiagnosticsBtn').addEventListener('click', function() {
    refreshDiagnostics('诊断信息已刷新');
  });
  document.querySelectorAll('.diagnostics-folder-form').forEach(function(form) {
    form.addEventListener('submit', function(event) {
      event.preventDefault();
      window.ContractToolApi.requestJson(form.action, {method: 'POST', body: new FormData(form)})
        .then(function(data) { showMessage('已请求打开目录：' + data.path, 'success'); })
        .catch(function(error) { showMessage(error.message || '打开目录失败', 'error'); });
    });
  });
  refreshDiagnostics('');
});
