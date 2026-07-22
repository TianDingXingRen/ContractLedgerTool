/** Payment-plan editor behavior for the contract detail page. */
'use strict';

(function contractDetailEditor() {
  const storageKey = 'contract-tool:payment-plan-column-widths:v1';
  const minColumnWidth = 48;
  const planCount = document.getElementById('plan_count');
  let planIndex = Number(planCount ? planCount.value : 0);

  function initColumnResize() {
    const table = document.querySelector('.payment-edit-table');
    if (!table || table.dataset.resizeReady === 'true') return;
    const columns = Array.from(table.querySelectorAll('colgroup col'));
    const handles = Array.from(table.querySelectorAll('.col-resize-handle'));
    if (!columns.length || !handles.length) return;
    table.dataset.resizeReady = 'true';
    let resizeState = null;

    function updateTableWidth() {
      const total = columns.reduce(function(sum, column) {
        return sum + (parseFloat(column.style.width) || column.getBoundingClientRect().width);
      }, 0);
      table.style.width = Math.ceil(total) + 'px';
    }

    try {
      const widths = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (Array.isArray(widths) && widths.length === columns.length) {
        widths.forEach(function(width, index) {
          if (Number.isFinite(width) && width >= minColumnWidth) columns[index].style.width = width + 'px';
        });
      }
    } catch (error) { console.warn('读取付款计划列宽失败', error); }
    updateTableWidth();

    handles.forEach(function(handle, index) {
      handle.addEventListener('mousedown', function(event) {
        event.preventDefault();
        event.stopPropagation();
        resizeState = {
          column: columns[index], handle: handle, startX: event.clientX,
          startWidth: columns[index].getBoundingClientRect().width,
        };
        handle.classList.add('active');
        table.classList.add('resizing');
        document.body.classList.add('column-resizing');
      });
    });
    document.addEventListener('mousemove', function(event) {
      if (!resizeState) return;
      resizeState.column.style.width = Math.round(Math.max(
        minColumnWidth, resizeState.startWidth + event.clientX - resizeState.startX,
      )) + 'px';
      updateTableWidth();
    });
    document.addEventListener('mouseup', function() {
      if (!resizeState) return;
      resizeState.handle.classList.remove('active');
      table.classList.remove('resizing');
      document.body.classList.remove('column-resizing');
      resizeState = null;
      try {
        localStorage.setItem(storageKey, JSON.stringify(columns.map(function(column) {
          return Math.round(column.getBoundingClientRect().width);
        })));
      } catch (error) { console.warn('保存付款计划列宽失败', error); }
    });
  }

  function optionHtml(options, selected) {
    return options.map(function(item) {
      return '<option value="' + item[0] + '"' + (item[0] === selected ? ' selected' : '') + '>' + item[1] + '</option>';
    }).join('');
  }

  function addPlanRow() {
    const body = document.getElementById('planRows');
    const empty = body.querySelector('.empty-cell');
    if (empty) empty.closest('tr').remove();
    const index = planIndex++;
    if (planCount) planCount.value = planIndex;
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><input type="hidden" name="plan_${index}_id" value=""><input type="hidden" name="plan_${index}_delete" value="0"><input name="plan_${index}_phase_name" value="" class="input input-bordered input-xs w-full"><input type="hidden" name="plan_${index}_confidence" value="low"><input type="hidden" name="plan_${index}_expected_trigger_date" value=""><input type="hidden" name="plan_${index}_amount_basis" value=""><input type="hidden" name="plan_${index}_explicit_amount" value=""><input type="hidden" name="plan_${index}_calculated_amount" value=""><input type="hidden" name="plan_${index}_parse_status" value="manual"><input type="hidden" name="plan_${index}_reason_codes_json" value="[]"><input type="hidden" name="plan_${index}_rule_fingerprint" value=""><input type="hidden" name="plan_${index}_extractor_version" value=""><span class="confidence-badge badge badge-ghost badge-xs mt-1">人工录入</span></td>
      <td><select name="plan_${index}_confirm_status" class="select select-bordered select-xs">${optionHtml([['pending','待确认'],['confirmed','已确认'],['void','已作废']], 'pending')}</select></td>
      <td><select name="plan_${index}_payment_status" class="select select-bordered select-xs">${optionHtml([['unpaid','未付款'],['partial','部分付款'],['paid','已付款']], 'unpaid')}</select></td>
      <td><select name="plan_${index}_payment_type" class="select select-bordered select-xs">${optionHtml([['conditional','条件触发'],['fixed_date','固定日期']], 'conditional')}</select></td>
      <td><input name="plan_${index}_trigger_event" class="input input-bordered input-xs w-20" title="触发条件"></td><td><input name="plan_${index}_trigger_days" class="input input-bordered input-xs w-16" title="后置天数"></td><td><input name="plan_${index}_due_date" placeholder="YYYY-MM-DD" class="input input-bordered input-xs w-24" title="预计付款日"></td><td><input name="plan_${index}_ratio" class="input input-bordered input-xs w-16" title="比例%"></td><td><input name="plan_${index}_due_amount" class="input input-bordered input-xs w-24" title="应付金额"></td><td><input name="plan_${index}_paid_amount" value="0" class="input input-bordered input-xs w-20" title="已付金额"></td><td><input name="plan_${index}_paid_date" placeholder="YYYY-MM-DD" class="input input-bordered input-xs w-24" title="实付日期"></td>
      <td><textarea name="plan_${index}_condition_text" rows="1" class="textarea textarea-bordered textarea-xs w-full" title="付款条件/备注"></textarea><input name="plan_${index}_remark" placeholder="备注" class="input input-bordered input-xs w-full mt-1" title="备注"></td><td><textarea name="plan_${index}_source_text" rows="1" class="textarea textarea-bordered textarea-xs w-full" title="原文依据"></textarea></td>
      <td><button type="button" class="btn btn-ghost btn-xs text-error" data-plan-action="remove"><i data-lucide="x" class="w-3 h-3"></i></button></td>`;
    body.appendChild(row);
  }

  async function removePlanRow(button) {
    const ok = await window.confirmAction('确定删除这条付款计划吗？保存后生效。', {
      title: '删除付款计划', confirmText: '删除', danger: true,
    });
    if (!ok) return;
    const row = button.closest('tr');
    const deleteInput = row.querySelector('input[name$="_delete"]');
    const idInput = row.querySelector('input[name$="_id"]');
    if (idInput && idInput.value) {
      deleteInput.value = '1';
      row.hidden = true;
    } else row.remove();
  }

  document.addEventListener('click', function(event) {
    const action = event.target.closest('[data-plan-action]');
    if (!action) return;
    if (action.dataset.planAction === 'add') addPlanRow();
    if (action.dataset.planAction === 'remove') removePlanRow(action);
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initColumnResize);
  else initColumnResize();
})();
