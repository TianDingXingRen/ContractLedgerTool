(function () {
    'use strict';

    var SELECTOR = '[data-coverage-mode]';

    function selectedMode(root) {
        var selected = root.querySelector('input[name="coverage_mode"]:checked');
        return selected ? selected.value : '';
    }

    function hintText(mode, lockedMode) {
        if (lockedMode === 'range') {
            return '发次适用性已锁定；仍可修正或扩展数字范围。';
        }
        if (lockedMode === 'not_applicable') {
            return '发次适用性已锁定为不适用。';
        }
        if (mode === 'range') {
            return '请同时填写起始发次和结束发次；数字发次合同还需填写项目名称。';
        }
        if (mode === 'not_applicable') {
            return '此合同不按发次归集，起始发次和结束发次无需填写。';
        }
        return '请选择填写数字范围或不适用。';
    }

    function sync(root) {
        if (!root) return;
        var mode = selectedMode(root);
        var lockedMode = root.dataset.coverageLocked || '';
        var isRange = mode === 'range';
        var isNotApplicable = mode === 'not_applicable';

        root.querySelectorAll('input[name="coverage_mode"]').forEach(function (radio) {
            var isLockedOut = Boolean(lockedMode && radio.value !== lockedMode);
            radio.disabled = isLockedOut;
            radio.setAttribute('aria-disabled', String(isLockedOut));
        });

        root.querySelectorAll('[data-coverage-bound]').forEach(function (input) {
            input.disabled = isNotApplicable;
            input.required = isRange;
            input.setAttribute('aria-disabled', String(isNotApplicable));
        });

        var form = root.closest('form');
        var projectInput = form ? form.querySelector('[data-coverage-project]') : null;
        if (projectInput) projectInput.required = isRange;

        root.querySelectorAll('[data-coverage-range-fields]').forEach(function (rangeFields) {
            rangeFields.setAttribute('aria-disabled', String(isNotApplicable));
            rangeFields.style.opacity = isNotApplicable ? '0.5' : '';
        });

        var hint = root.querySelector('[data-coverage-hint]');
        if (hint) hint.textContent = hintText(mode, lockedMode);
    }

    function bind(root) {
        if (!root || root.dataset.coverageBound === '1') return;
        root.dataset.coverageBound = '1';
        var details = root.closest('details');
        var reveal = function () {
            if (details) details.open = true;
        };
        root.addEventListener('change', function (event) {
            if (event.target.matches('input[name="coverage_mode"]')) sync(root);
        });
        root.addEventListener('invalid', reveal, true);
        var form = root.closest('form');
        var projectInput = form ? form.querySelector('[data-coverage-project]') : null;
        if (projectInput) projectInput.addEventListener('invalid', reveal);
        sync(root);
    }

    function syncAll(scope) {
        (scope || document).querySelectorAll(SELECTOR).forEach(sync);
    }

    function initialize(scope) {
        (scope || document).querySelectorAll(SELECTOR).forEach(bind);
    }

    window.CoverageMode = Object.freeze({
        initialize: initialize,
        sync: sync,
        syncAll: syncAll,
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { initialize(document); });
    } else {
        initialize(document);
    }
})();
