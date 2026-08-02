(function initInvoiceForm() {
  'use strict';

  const MAX_ALLOCATION_ROWS = 100;
  const targetRequests = new WeakMap();
  const invoiceForm = document.getElementById('invoice-form');
  const submitButtonStates = new Map();
  let pendingTargetLoads = 0;

  function showError(message) {
    if (typeof window.showToast === 'function') {
      window.showToast(message, 'error');
    } else {
      console.error(message);
    }
  }

  function beginTargetLoading() {
    pendingTargetLoads += 1;
    if (pendingTargetLoads !== 1 || !invoiceForm) return;
    invoiceForm.setAttribute('aria-busy', 'true');
    invoiceForm.querySelectorAll('[type="submit"]').forEach(function disableSubmit(button) {
      submitButtonStates.set(button, button.disabled);
      button.disabled = true;
    });
  }

  function endTargetLoading() {
    pendingTargetLoads = Math.max(0, pendingTargetLoads - 1);
    if (pendingTargetLoads !== 0 || !invoiceForm) return;
    invoiceForm.removeAttribute('aria-busy');
    submitButtonStates.forEach(function restoreSubmit(wasDisabled, button) {
      button.disabled = wasDisabled;
    });
    submitButtonStates.clear();
  }

  if (invoiceForm) {
    invoiceForm.addEventListener('submit', function preventSubmitWhileLoading(event) {
      if (pendingTargetLoads === 0) return;
      event.preventDefault();
      showError('合同关联项仍在加载，请稍候再保存');
    });
  }

  const currencyField = document.querySelector('[name="currency"]');
  if (currencyField) {
    currencyField.value = 'CNY';
    currencyField.readOnly = true;
    currencyField.setAttribute('aria-readonly', 'true');
    currencyField.title = '发票币种固定为人民币（CNY）';
  }

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

  function replaceOptions(select, items, emptyLabel, contractId, selectedValue) {
    const previous = selectedValue === undefined
      ? select.value
      : String(selectedValue || '');
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

  function setSelectLoading(select, loading, emptyLabel) {
    if (loading) {
      select.setAttribute('aria-busy', 'true');
    } else {
      select.removeAttribute('aria-busy');
    }
    const empty = Array.from(select.options).find(option => option.value === '');
    if (empty && emptyLabel) empty.textContent = emptyLabel;
  }

  async function loadTargets(row) {
    const contractField = row.querySelector('.allocation-contract');
    const contract = contractField.value;
    const noticeField = row.querySelector('.allocation-notice');
    const planField = row.querySelector('.allocation-plan');
    const previousNoticeId = noticeField.value;
    const previousPlanId = planField.value;
    const previousController = targetRequests.get(row);
    if (previousController) previousController.abort();
    if (!contract) {
      targetRequests.delete(row);
      replaceOptions(noticeField, [], '不关联', '');
      replaceOptions(planField, [], '不关联', '');
      setSelectLoading(noticeField, false);
      setSelectLoading(planField, false);
      return true;
    }
    const controller = new AbortController();
    targetRequests.set(row, controller);
    setSelectLoading(noticeField, true, '加载中…');
    setSelectLoading(planField, true, '加载中…');
    beginTargetLoading();
    try {
      const response = await fetch(
        `/api/contracts/${encodeURIComponent(contract)}/invoice-targets`,
        {
          headers: { Accept: 'application/json' },
          signal: controller.signal
        }
      );
      const data = await response.json().catch(function invalidJson() { return {}; });
      if (!response.ok) {
        throw new Error(data.error || `请求失败（${response.status}）`);
      }
      if (targetRequests.get(row) !== controller || contractField.value !== contract) {
        return false;
      }
      replaceOptions(
        noticeField,
        data.notices || [],
        '不关联',
        contract,
        previousNoticeId
      );
      replaceOptions(
        planField,
        data.plans || [],
        '不关联',
        contract,
        previousPlanId
      );
      setSelectLoading(noticeField, false);
      setSelectLoading(planField, false);
      return true;
    } catch (error) {
      if (error.name === 'AbortError') return false;
      if (targetRequests.get(row) === controller && contractField.value === contract) {
        setSelectLoading(noticeField, false, '加载失败');
        setSelectLoading(planField, false, '加载失败');
        showError(`加载合同关联项失败：${error.message}`);
      }
      return false;
    } finally {
      if (targetRequests.get(row) === controller) targetRequests.delete(row);
      endTargetLoading();
    }
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

  if (Number(countInput.value) >= MAX_ALLOCATION_ROWS) {
    addButton.disabled = true;
    addButton.title = `最多只能添加 ${MAX_ALLOCATION_ROWS} 行分摊`;
  }

  addButton.addEventListener('click', function addAllocation() {
    const index = Number(countInput.value);
    if (!Number.isInteger(index) || index < 0) {
      showError('当前分摊行数无效，请刷新页面后重试');
      return;
    }
    if (index >= MAX_ALLOCATION_ROWS) {
      showError(`最多只能添加 ${MAX_ALLOCATION_ROWS} 行分摊`);
      return;
    }
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
    if (index + 1 >= MAX_ALLOCATION_ROWS) {
      addButton.disabled = true;
      addButton.title = `最多只能添加 ${MAX_ALLOCATION_ROWS} 行分摊`;
      showError(`已达到 ${MAX_ALLOCATION_ROWS} 行分摊上限`);
    }
    loadTargets(row).then(function targetsLoaded() { filterRow(row); });
  });
})();
