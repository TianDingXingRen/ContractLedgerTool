/** Dashboard Alpine components. */
'use strict';

var autostartConfigElement = document.getElementById('autostartConfig');
var autostartConfig = JSON.parse(autostartConfigElement ? autostartConfigElement.textContent : '{}');

document.addEventListener('alpine:init', function() {
  Alpine.data('autostartToggle', function(initialOn, supported) {
    return {
      on: initialOn,
      supported: supported,
      busy: false,
      ready: !supported,
      err: '',
      init: function() {
        var self = this;
        if (!self.supported) return;
        self.busy = true;
        window.ContractToolApi.requestJson(autostartConfig.status, {headers: {'Accept': 'application/json'}})
          .then(function(data) {
            if (!data.success) throw new Error(data.message || '自启动状态检测失败');
            self.on = !!data.enabled;
          }).catch(function(error) { self.err = error.message; })
          .finally(function() { self.ready = true; self.busy = false; });
      },
      toggle: function() {
        var self = this;
        if (self.busy || !self.supported || !self.ready) return;
        clearTimeout(self._timer);
        self.busy = true;
        self.err = '';
        var previous = self.on;
        self.on = !self.on;
        var url = self.on ? autostartConfig.enable : autostartConfig.disable;
        window.ContractToolApi.requestJson(url, {
          method: 'POST',
          body: new URLSearchParams({csrf_token: window.ContractToolApi.csrfToken()}),
        }).then(function(data) {
          if (!data.success) throw new Error(data.message || '操作失败');
          self.on = !!data.enabled;
        }).catch(function(error) {
          self.on = previous;
          self.err = error.message;
        }).finally(function() {
          self._timer = setTimeout(function() { self.busy = false; }, 300);
        });
      },
    };
  });
});
