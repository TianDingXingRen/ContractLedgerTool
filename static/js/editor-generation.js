/** Editor-specific API requests. */
'use strict';

(function registerGenerationApi(editor, api) {
  function saveDefaults(form) {
    return api.requestJson(editor.config.urls.saveDefaults, {
      method: 'POST',
      body: new FormData(form),
    });
  }

  function preflight(form, isBatch) {
    var formData = new FormData(form);
    formData.append('_generation_mode', isBatch ? 'batch' : 'single');
    return api.request(editor.config.urls.generatePreflight, {
      method: 'POST',
      body: formData,
    }).then(function(response) {
      return response.text().then(function(text) {
        var payload;
        try { payload = JSON.parse(text || '{}'); } catch (error) {
          payload = {ok: false, blocking: [api.responseMessage(response, text)], warnings: []};
        }
        payload._statusOk = response.ok;
        return payload;
      });
    });
  }

  function generate(url, formData) {
    return api.request(url, {method: 'POST', body: formData});
  }

  editor.generation = Object.freeze({
    saveDefaults: saveDefaults,
    preflight: preflight,
    generate: generate,
  });
})(window.ContractEditor, window.ContractToolApi);
