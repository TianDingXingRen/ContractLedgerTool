(function initContractItems() {
  'use strict';

  const MAX_ITEM_ROWS = 500;
  const addButton = document.getElementById('add-item-row');
  const countInput = document.getElementById('item-count');
  const rows = document.getElementById('item-rows');
  if (!addButton || !countInput || !rows) return;

  function showLimitError() {
    const message = `合同产品最多只能维护 ${MAX_ITEM_ROWS} 行`;
    if (typeof window.showToast === 'function') {
      window.showToast(message, 'error');
    } else {
      console.error(message);
    }
  }

  if (Number(countInput.value) >= MAX_ITEM_ROWS) {
    addButton.disabled = true;
    addButton.title = `最多只能添加 ${MAX_ITEM_ROWS} 行产品`;
  }

  addButton.addEventListener('click', function addItemRow() {
    const index = Number(countInput.value);
    if (!Number.isInteger(index) || index < 0) {
      showLimitError();
      return;
    }
    if (index >= MAX_ITEM_ROWS) {
      showLimitError();
      return;
    }
    const row = document.createElement('tr');
    row.dataset.itemRow = '';
    row.innerHTML = `
      <td><input type="hidden" name="item_${index}_id"><input class="input input-bordered input-sm w-16" name="item_${index}_line_no" value="${index + 1}"></td>
      <td><input class="input input-bordered input-sm min-w-40" name="item_${index}_item_name" required></td>
      <td><input class="input input-bordered input-sm min-w-32" name="item_${index}_spec_model"></td>
      <td><input class="input input-bordered input-sm w-28" name="item_${index}_drawing_no"></td>
      <td><input class="input input-bordered input-sm w-24" name="item_${index}_contracted_qty" inputmode="numeric"></td>
      <td><input class="input input-bordered input-sm w-16" name="item_${index}_unit" value="个"></td>
      <td><input class="input input-bordered input-sm w-24" name="item_${index}_serial_start" inputmode="numeric"></td>
      <td><input class="input input-bordered input-sm w-24" name="item_${index}_serial_end" inputmode="numeric"></td>
      <td><input class="input input-bordered input-sm w-28" name="item_${index}_unit_price" inputmode="decimal"></td>
      <td>—</td><td>0</td><td>—</td><td></td>`;
    rows.appendChild(row);
    countInput.value = index + 1;
    if (index + 1 >= MAX_ITEM_ROWS) {
      addButton.disabled = true;
      addButton.title = `最多只能添加 ${MAX_ITEM_ROWS} 行产品`;
    }
  });
})();
