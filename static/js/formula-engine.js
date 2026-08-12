/**
 * formula-engine.js - 安全公式求值引擎
 * 与后端 field_eval.py 保持一致: + - * / () SUM/AVG/MAX/MIN/COUNT
 */
(function () {
  'use strict';

  var MAX_ABS_NUMBER = 1000000000000;
  var MAX_FORMULA_LENGTH = 500;
  var MAX_FUNC_ARGS = 100;
  var MAX_RELIABLE_DIGITS = 15;

  function checkedNumber(value) {
    if (!Number.isFinite(value)) throw new Error('计算结果无效');
    if (Math.abs(value) > MAX_ABS_NUMBER) throw new Error('数值超出范围');
    return value;
  }

  function decimalTextNumber(value) {
    if (typeof value === 'number') return checkedNumber(value);
    var text = String(value == null ? '' : value).trim();
    if (!/^[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?$/.test(text)) {
      throw new Error('不是有效数字');
    }
    return checkedNumber(Number(text));
  }

  // Match utils.field_utils.to_calc_number for editable scalar/table cells.
  function appInputNumber(value) {
    if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
    var text = String(value == null ? '' : value).trim().replace(/,/g, '');
    var percent = text.endsWith('%');
    if (percent) text = text.substring(0, text.length - 1);
    try {
      var parsed = decimalTextNumber(text);
      return checkedNumber(percent ? parsed / 100 : parsed);
    } catch (error) {
      return 0;
    }
  }

  // Table aggregates in field_eval resolve raw row values directly; unlike
  // editable cell calculations, comma/percent strings are invalid and become 0.
  function strictTableNumber(value) {
    try { return decimalTextNumber(value); } catch (error) { return 0; }
  }

  // ── 安全的四则运算求值器（不依赖 eval/Function）──
  function _safeArithEval(expr) {
    var pos = 0;
    function peek() { return pos < expr.length ? expr[pos] : ''; }
    function consume() { return expr[pos++]; }
    function skipWs() { while (/\s/.test(peek())) consume(); }

    function parseExpr() {
      var left = parseTerm();
      while (true) {
        skipWs();
        var op = peek();
        if (op === '+' || op === '-') {
          consume();
          var right = parseTerm();
          left = checkedNumber(op === '+' ? left + right : left - right);
        } else break;
      }
      return left;
    }

    function parseTerm() {
      var left = parseFactor();
      while (true) {
        skipWs();
        var op = peek();
        if (op === '*' || op === '/') {
          consume();
          var right = parseFactor();
          if (op === '/' && right === 0) throw new Error('除以零');
          left = checkedNumber(op === '*' ? left * right : left / right);
        } else break;
      }
      return left;
    }

    function parseFactor() {
      skipWs();
      var ch = peek();
      if (ch === '(') {
        consume();
        var value = parseExpr();
        skipWs();
        if (peek() !== ')') throw new Error('公式括号不匹配');
        consume();
        return value;
      }
      if (ch === '-') { consume(); return checkedNumber(-parseFactor()); }
      if (ch === '+') { consume(); return parseFactor(); }
      var match = expr.substring(pos).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?/);
      if (!match) throw new Error('公式包含无效字符');
      pos += match[0].length;
      return decimalTextNumber(match[0]);
    }

    var result = parseExpr();
    skipWs();
    if (pos !== expr.length) throw new Error('公式包含多余字符');
    return checkedNumber(result);
  }

  function aggregateNumber(name, values) {
    if (name === 'COUNT') return values.length;
    if (!values.length) return 0;
    if (name === 'MAX') return checkedNumber(Math.max.apply(null, values));
    if (name === 'MIN') return checkedNumber(Math.min.apply(null, values));
    var total = values.reduce(function(sum, value) {
      return checkedNumber(sum + value);
    }, 0);
    return name === 'AVG' ? checkedNumber(total / values.length) : total;
  }

  function safeEval(expr, context) {
    if (!expr || !String(expr).trim()) return 0;
    expr = String(expr).trim();
    context = context || {};
    if (expr.length > MAX_FORMULA_LENGTH) throw new Error('公式过长');
    if (/[^0-9a-zA-Z_一-鿿+\-*/().,\s]/.test(expr)) throw new Error('公式包含无效字符');

    function extractFuncCall(str, startIdx) {
      var depth = 0;
      for (var index = startIdx; index < str.length; index++) {
        if (str[index] === '(') depth++;
        else if (str[index] === ')') {
          depth--;
          if (depth === 0) return str.substring(startIdx + 1, index);
        }
      }
      throw new Error('公式括号不匹配');
    }

    function splitArgs(argsText) {
      if (!argsText.trim()) return [];
      var parts = [];
      var depth = 0;
      var start = 0;
      for (var index = 0; index < argsText.length; index++) {
        if (argsText[index] === '(') depth++;
        else if (argsText[index] === ')') depth--;
        else if (argsText[index] === ',' && depth === 0) {
          parts.push(argsText.substring(start, index).trim());
          start = index + 1;
        }
      }
      parts.push(argsText.substring(start).trim());
      if (parts.length > MAX_FUNC_ARGS) throw new Error('函数参数过多');
      return parts;
    }

    var funcPattern = /(SUM|AVG|MAX|MIN|COUNT)\(/g;
    var funcMatch;
    while ((funcMatch = funcPattern.exec(expr)) !== null) {
      var funcName = funcMatch[1];
      var openIdx = funcMatch.index + funcName.length;
      var argsText = extractFuncCall(expr, openIdx);
      var args = splitArgs(argsText);
      var replacement;
      var tableContext = args.length === 2 ? context[args[0]] : null;
      if (tableContext && tableContext.__tableRows) {
        if (tableContext.__tableColumns.indexOf(args[1]) === -1) {
          throw new Error('表格中不存在列 ' + args[1]);
        }
        replacement = aggregateNumber(funcName, tableContext.__tableRows.map(function(row) {
          return strictTableNumber(row[args[1]]);
        }));
      } else {
        replacement = aggregateNumber(funcName, args.map(function(arg) {
          return safeEval(arg, context);
        }));
      }
      expr = expr.substring(0, funcMatch.index) + String(replacement) +
        expr.substring(openIdx + argsText.length + 2);
      funcPattern.lastIndex = 0;
    }

    // Replace longer keys first so a short key cannot corrupt a longer one.
    var resolved = expr;
    Object.keys(context).sort(function(a, b) { return b.length - a.length; }).forEach(function(key) {
      if (!key || (context[key] && context[key].__tableRows)) return;
      var escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      var unicodes = '一-鿿';
      var re = new RegExp('(?<![\\w' + unicodes + '])' + escaped + '(?![\\w' + unicodes + '])', 'g');
      resolved = resolved.replace(re, String(appInputNumber(context[key])));
    });

    var sanitized = resolved.replace(/\s+/g, '');
    if (!/^[0-9eE+\-*/().]+$/.test(sanitized)) throw new Error('公式包含无效字符');
    return _safeArithEval(sanitized);
  }

  function normalizedPlaces(decimals) {
    var numeric = Number(decimals);
    return Number.isFinite(numeric) ? Math.max(0, Math.min(6, Math.trunc(numeric))) : 2;
  }

  function assertReliableFixedPrecision(value, places) {
    var absolute = Math.abs(value);
    var integerDigits = absolute < 1 ? 1 : Math.floor(Math.log10(absolute)) + 1;
    if (integerDigits + places > MAX_RELIABLE_DIGITS) {
      throw new Error('数值超出前端精确预览范围，请以生成结果为准');
    }
  }

  // Number remains the browser arithmetic type, but unreliable high-magnitude
  // fixed-point previews are rejected instead of displaying a value that may
  // disagree with backend Decimal/ROUND_HALF_UP.
  function roundHalfUp(value, decimals) {
    var numeric = checkedNumber(Number(value));
    var places = normalizedPlaces(decimals);
    assertReliableFixedPrecision(numeric, places);
    var factor = Math.pow(10, places);
    var scaled = numeric * factor;
    var tolerance = Number.EPSILON * Math.max(1, Math.abs(scaled));
    var rounded = scaled >= 0
      ? Math.floor(scaled + 0.5 + tolerance)
      : Math.ceil(scaled - 0.5 - tolerance);
    return rounded / factor;
  }

  function formatNumber(value, decimals) {
    var places = normalizedPlaces(decimals);
    return roundHalfUp(value, places).toFixed(places);
  }

  function buildCalcContext(fieldDefs) {
    var context = {};
    fieldDefs.forEach(function (field) {
      var key = field.key;
      if (!key) return;
      var item = document.getElementById('field_' + field.id);
      if (!item) return;
      var input = item.querySelector('.field-input, .field-select, textarea');
      if (field.field_type === 'table') {
        try {
          var dataElement = document.getElementById('table_data_' + field.id);
          var data = JSON.parse((dataElement && dataElement.value) || '[]');
          context[key] = {
            __tableRows: data,
            __tableColumns: (field.columns || []).map(function (column) { return column.key; })
          };
        } catch (error) {}
      } else if (field.field_type === 'calculated') {
        context[key] = 0;
      } else if (input) {
        context[key] = input.value || 0;
      }
    });
    return context;
  }

  function calcFieldDefinition(element, fieldDefs) {
    var fieldId = String(element.id || '').replace(/^calc_/, '');
    return fieldDefs.find(function (field) { return String(field.id) === fieldId; }) || null;
  }

  function sortedCalcElements(fieldDefs, elements) {
    var byKey = {};
    elements.forEach(function (element) {
      var field = calcFieldDefinition(element, fieldDefs);
      if (field && field.key) byKey[field.key] = { field: field, element: element };
    });
    var ordered = [];
    var state = {};
    function visit(key) {
      if (state[key] === 2) return;
      if (state[key] === 1) return;
      var entry = byKey[key];
      if (!entry) return;
      state[key] = 1;
      var dependencies = entry.field.depends_on || [];
      if (!Array.isArray(dependencies)) dependencies = [];
      dependencies.forEach(function (dependency) { visit(String(dependency)); });
      state[key] = 2;
      ordered.push(entry.element);
    }
    Object.keys(byKey).forEach(visit);
    elements.forEach(function (element) {
      if (ordered.indexOf(element) === -1) ordered.push(element);
    });
    return ordered;
  }

  function evaluateCalcField(element, context, fieldDefs) {
    var fieldId = String(element.id || '').replace(/^calc_/, '');
    var formula = element.dataset.formula;
    var decimals = parseInt(element.dataset.decimals || 2);
    var field = calcFieldDefinition(element, fieldDefs);
    try {
      var result = safeEval(formula, context);
      var formatted = formatNumber(result, decimals);
      element.value = formatted;
      var hiddenInput = document.getElementById('calc_input_' + fieldId);
      if (hiddenInput) hiddenInput.value = formatted;
      if (field && field.key) context[field.key] = formatted;
      return formatted;
    } catch (error) {
      element.value = '';
      element.placeholder = 'error';
      if (field && field.key) context[field.key] = 0;
      return '';
    }
  }

  function recalcField(element) {
    var fieldDefs = (window.ContractEditor && window.ContractEditor.config.fields) || [];
    var context = buildCalcContext(fieldDefs);
    return evaluateCalcField(element, context, fieldDefs);
  }

  function recalcAllFields() {
    var fieldDefs = (window.ContractEditor && window.ContractEditor.config.fields) || [];
    var elements = Array.from(document.querySelectorAll('.calc-result'));
    var context = buildCalcContext(fieldDefs);
    sortedCalcElements(fieldDefs, elements).forEach(function (element) {
      evaluateCalcField(element, context, fieldDefs);
    });
  }

  function triggerCalc(changedId) {
    var fieldDefs = (window.ContractEditor && window.ContractEditor.config.fields) || [];
    var normalizedChangedId = String(changedId);
    var changedField = fieldDefs.find(function (field) {
      return String(field.id) === normalizedChangedId;
    });
    if (!changedField || !changedField.key) return;
    recalcAllFields();
  }

  function formulaDependencies(formula) {
    var dependencies = [];
    var seen = {};
    var functions = {SUM: true, AVG: true, MAX: true, MIN: true, COUNT: true};
    var tokenPattern = /(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*)/g;
    var match;
    while ((match = tokenPattern.exec(String(formula || ''))) !== null) {
      var name = match[1];
      if (!name || functions[name] || seen[name]) continue;
      seen[name] = true;
      dependencies.push(name);
    }
    return dependencies;
  }

  function sortTableColumnsByDependency(columns) {
    columns = columns || [];
    var allKeys = {};
    var resolved = {};
    var inputColumns = [];
    var remaining = [];
    columns.forEach(function(column) {
      if (!column || !column.key) {
        if (column && column.field_type === 'calculated') {
          throw new Error('计算列缺少 key');
        }
        return;
      }
      if (allKeys[column.key]) throw new Error('表格列 key 重复: ' + column.key);
      allKeys[column.key] = true;
      if (column.field_type === 'calculated') {
        if (!String(column.formula || '').trim()) {
          throw new Error((column.label || column.key) + ' 缺少公式');
        }
        remaining.push(column);
      } else {
        inputColumns.push(column);
        resolved[column.key] = true;
      }
    });

    var ordered = [];
    while (remaining.length) {
      var nextRemaining = [];
      var progressed = false;
      remaining.forEach(function(column) {
        var dependencies = formulaDependencies(column.formula);
        if (dependencies.every(function(key) { return resolved[key]; })) {
          ordered.push(column);
          resolved[column.key] = true;
          progressed = true;
        } else {
          nextRemaining.push(column);
        }
      });
      remaining = nextRemaining;
      if (!progressed) break;
    }

    if (remaining.length) {
      var problems = remaining.map(function(column) {
        var missing = formulaDependencies(column.formula).filter(function(key) {
          return !allKeys[key];
        });
        return (column.label || column.key || '未命名列') +
          (missing.length ? ' 缺少依赖: ' + missing.join(', ') : ' 存在循环依赖');
      });
      throw new Error(problems.join('；'));
    }
    return inputColumns.concat(ordered);
  }

  function calculateTableRow(columns, initialContext) {
    var context = {};
    (columns || []).forEach(function(column) {
      if (column.field_type !== 'calculated' && column.key) {
        context[column.key] = Object.prototype.hasOwnProperty.call(initialContext || {}, column.key)
          ? initialContext[column.key]
          : 0;
      }
    });
    var formatted = {};
    sortTableColumnsByDependency(columns).forEach(function (column) {
      if (column.field_type !== 'calculated' || !column.key || !column.formula) return;
      try {
        var result = safeEval(column.formula, context);
        var text = formatNumber(result, column.decimal_places == null ? 2 : column.decimal_places);
        formatted[column.key] = text;
        context[column.key] = text;
      } catch (error) {
        formatted[column.key] = '?';
      }
    });
    return formatted;
  }

  window.ContractFormulaEngine = Object.freeze({
    safeEval: safeEval,
    roundHalfUp: roundHalfUp,
    formatNumber: formatNumber,
    sortTableColumnsByDependency: sortTableColumnsByDependency,
    calculateTableRow: calculateTableRow,
    recalcField: recalcField,
    recalcAllFields: recalcAllFields,
    triggerCalc: triggerCalc,
  });
})();
