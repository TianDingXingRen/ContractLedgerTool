(function initInvoiceForm() {
  'use strict';

  function filterRow(row) {
    const contractField = row.querySelector('.allocation-contract');
    if (!contractField) return;
    const contract = contractField.value;
    row.querySelectorAll(
      '.allocation-notice option[data-contract], .allocation-plan option[data-contract]'
    ).forEach(function setOptionVisibility(option) {
      option.hidden = Boolean(contract) && option.dataset.contract !== contract;
    });
  }

  function replaceOptions(select, items, emptyLabel, contractId) {
    const previous = select.value;
    select.replaceChildren();
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = emptyLabel;
    select.appendChild(empty);
    items.forEach(function addOption(item) {
      const option = document.createElement('option');
      option.value = String(item.id);
      option.textContent = item.label;
      option.dataset.contract = contractId;
      select.appendChild(option);
    });
    if (Array.from(select.options).some(option => option.value === previous)) {
      select.value = previous;
    }
  }

  async function loadTargets(row) {
    const contract = row.querySelector('.allocation-contract').value;
    if (!contract) {
      replaceOptions(row.querySelector('.allocation-notice'), [], '不关联', '');
      replaceOptions(row.querySelector('.allocation-plan'), [], '不关联', '');
      return;
    }
    const response = await fetch(`/api/contracts/${encodeURIComponent(contract)}/invoice-targets`, {
      headers: { Accept: 'application/json' }
    });
    if (!response.ok) return;
    const data = await response.json();
    replaceOptions(row.querySelector('.allocation-notice'), data.notices || [], '不关联', contract);
    replaceOptions(row.querySelector('.allocation-plan'), data.plans || [], '不关联', contract);
  }

  document.querySelectorAll('[data-allocation-row]').forEach(function initializeRow(row) {
    const contractField = row.querySelector('.allocation-contract');
    contractField.addEventListener('change', async function handleContractChange() {
      await loadTargets(row);
      filterRow(row);
    });
    filterRow(row);
  });

  const addButton = document.getElementById('add-allocation');
  const countInput = document.getElementById('allocation-count');
  const rows = document.getElementById('allocation-rows');
  if (!addButton || !countInput || !rows) return;

  addButton.addEventListener('click', function addAllocation() {
    const index = Number(countInput.value);
    const first = document.querySelector('[data-allocation-row]');
    if (!first) return;
    const row = first.cloneNode(true);
    row.querySelectorAll('select,input').forEach(function resetField(field) {
      field.name = field.name.replace(/allocation_\d+_/, `allocation_${index}_`);
      field.value = '';
    });
    row.querySelector('.allocation-contract').addEventListener(
      'change',
      async function handleContractChange() {
        await loadTargets(row);
        filterRow(row);
      }
    );
    rows.appendChild(row);
    countInput.value = index + 1;
    loadTargets(row).then(function targetsLoaded() { filterRow(row); });
  });
})();
