(function () {
    'use strict';

    function fieldDefaults() {
        var element = document.getElementById('contract-payment-field-data');
        if (!element) return {};
        try {
            return JSON.parse(element.textContent || '{}');
        } catch (_error) {
            return {};
        }
    }

    function enhancePaymentFields() {
        var subsystemByDrawer = fieldDefaults();
        document.querySelectorAll('select[name="plan_0_contract_serial_id"]').forEach(function (select) {
            var launchField = select.closest('label');
            var dialog = select.closest('dialog');
            if (!launchField || !dialog) return;

            var launchLabel = launchField.querySelector('span');
            if (launchLabel) launchLabel.textContent = '所属发次';
            var hint = launchField.querySelector('small');
            if (hint) hint.textContent = '月度模板按此发次归集付款节点';
            Array.from(select.options).forEach(function (option) {
                if (!option.value) {
                    option.textContent = '待补发次';
                    return;
                }
                option.textContent = option.textContent.replace(
                    /^\s*(\d+)号/,
                    '第 $1 发'
                );
            });

            var subsystemField = document.createElement('label');
            subsystemField.className = 'ui-field span-2';
            var subsystemLabel = document.createElement('span');
            subsystemLabel.textContent = '所属分系统';
            var subsystemInput = document.createElement('input');
            subsystemInput.className = 'ui-input';
            subsystemInput.name = 'plan_0_subsystem_name';
            subsystemInput.maxLength = 120;
            subsystemInput.placeholder = '选填';
            subsystemInput.value = subsystemByDrawer[dialog.id] || '';
            subsystemField.appendChild(subsystemLabel);
            subsystemField.appendChild(subsystemInput);
            launchField.parentNode.insertBefore(subsystemField, launchField);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', enhancePaymentFields);
    } else {
        enhancePaymentFields();
    }
})();
