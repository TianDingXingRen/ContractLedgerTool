/** Shared same-origin API helpers with CSRF and normalized error handling. */
'use strict';

(function initContractToolApi(global) {
  function csrfToken() {
    var input = document.querySelector('input[name="csrf_token"]');
    var meta = document.querySelector('meta[name="csrf-token"]');
    return input ? input.value : (meta ? meta.content : '');
  }

  function escapeHtml(value) {
    var element = document.createElement('div');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
  }

  function responseMessage(response, text) {
    var payload;
    try { payload = JSON.parse(text || '{}'); } catch (error) { payload = null; }
    return (payload && (payload.message || payload.error)) ||
      String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().substring(0, 300) ||
      ('请求失败（HTTP ' + response.status + '）');
  }

  function request(url, options) {
    var opts = Object.assign({}, options || {});
    var method = String(opts.method || 'GET').toUpperCase();
    var headers = new Headers(opts.headers || {});
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers.has('X-CSRF-Token')) {
      var token = csrfToken();
      if (token) headers.set('X-CSRF-Token', token);
    }
    headers.set('X-Requested-With', 'XMLHttpRequest');
    opts.headers = headers;
    return fetch(url, opts);
  }

  function requestJson(url, options) {
    return request(url, options).then(function(response) {
      return response.text().then(function(text) {
        var payload;
        try { payload = JSON.parse(text || '{}'); } catch (error) { payload = null; }
        if (!response.ok || !payload) throw new Error(responseMessage(response, text));
        return payload;
      });
    });
  }

  global.ContractToolApi = Object.freeze({
    csrfToken: csrfToken,
    escapeHtml: escapeHtml,
    request: request,
    requestJson: requestJson,
    responseMessage: responseMessage,
  });
})(window);
