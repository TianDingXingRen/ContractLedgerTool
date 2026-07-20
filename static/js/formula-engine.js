/**
 * formula-engine.js - 安全公式求值引擎
 * 与后端 field_eval.py 保持一致: + - * / () SUM/AVG/MAX/MIN/COUNT
 */
(function () {
  'use strict';

  // ── 安全的四则运算求值器（不依赖 eval/Function）──
  function _safeArithEval(expr) {
    var pos = 0;
    function peek() { return pos < expr.length ? expr[pos] : ''; }
    function consume() { return expr[pos++]; }
    function skipWs() { while (peek() === ' ') consume(); }

    function parseExpr() {
      var left = parseTerm();
      while (true) {
        skipWs();
        var op = peek();
        if (op === '+' || op === '-') { consume(); var right = parseTerm(); left = op === '+' ? left + right : left - right; }
        else break;
      }
      return left;
    }

    function parseTerm() {
      var left = parseFactor();
      while (true) {
        skipWs();
        var op = peek();
        if (op === '*' || op === '/') { consume(); var right = parseFactor(); if (op === '/' && right === 0) throw new Error('除以零'); left = op === '*' ? left * right : left / right; }
        else break;
      }
      return left;
    }

    function parseFactor() {
      skipWs();
      var ch = peek();
      if (ch === '(') { consume(); var val = parseExpr(); skipWs(); if (peek() === ')') consume(); return val; }
      if (ch === '-') { consume(); return -parseFactor(); }
      if ((ch >= '0' && ch <= '9') || ch === '.') {
        var start = pos;
        while ((peek() >= '0' && peek() <= '9') || peek() === '.') { consume(); }
        return parseFloat(expr.substring(start, pos));
      }
      throw new Error('Unexpected: ' + ch);
    }

    var result = parseExpr();
    skipWs();
    if (pos !== expr.length) throw new Error('Trailing characters');
    return result;
  }

  function safeEval(expr, context) {
    if (!expr || !expr.trim()) return 0;
    expr = expr.trim();
    // 拒绝含危险字符的表达式
    if (/[^0-9a-zA-Z_一-鿿+\-*/().,\s]/.test(expr)) return 0;

    var aggFuncs = {
      SUM: function (arr) { return arr.reduce(function (a, b) { return a + b; }, 0); },
      AVG: function (arr) { return arr.length ? arr.reduce(function (a, b) { return a + b; }, 0) / arr.length : 0; },
      MAX: function (arr) { return arr.length ? Math.max.apply(null, arr) : 0; },
      MIN: function (arr) { return arr.length ? Math.min.apply(null, arr) : 0; },
      COUNT: function (arr) { return arr.length; }
    };

    // 使用括号层级计数提取函数参数，正确处理嵌套括号如 SUM(a * (b + c), d)
    function _extractFuncCall(str, startIdx) {
      // startIdx 指向函数名后的 '('
      var depth = 0;
      var i = startIdx;
      for (; i < str.length; i++) {
        if (str[i] === '(') depth++;
        else if (str[i] === ')') { depth--; if (depth === 0) return str.substring(startIdx + 1, i); }
      }
      return str.substring(startIdx + 1); // 未闭合时尽力返回
    }
    function _splitArgs(argsStr) {
      // 按顶层逗号分割，忽略括号内的逗号
      var parts = []; var depth = 0; var start = 0;
      for (var i = 0; i < argsStr.length; i++) {
        if (argsStr[i] === '(') depth++;
        else if (argsStr[i] === ')') depth--;
        else if (argsStr[i] === ',' && depth === 0) { parts.push(argsStr.substring(start, i).trim()); start = i + 1; }
      }
      parts.push(argsStr.substring(start).trim());
      return parts;
    }
    var funcPattern = /(SUM|AVG|MAX|MIN|COUNT)\(/g;
    var funcMatch;
    while ((funcMatch = funcPattern.exec(expr)) !== null) {
      var funcName = funcMatch[1];
      var openIdx = funcMatch.index + funcName.length;
      var argsStr = _extractFuncCall(expr, openIdx);
      var fullMatch = expr.substring(funcMatch.index, openIdx + argsStr.length + 2); // FUNC( ... )
      var argNames = _splitArgs(argsStr);
      var replacement;
      if (argNames.length === 2 && context[argNames[0]] && context[argNames[0]].__tableRows) {
        var tableContext = context[argNames[0]];
        if (tableContext.__tableColumns.indexOf(argNames[1]) === -1) { replacement = '0'; }
        else {
          var columnValues = tableContext.__tableRows.map(function (row) {
            return parseFloat(row[argNames[1]]) || 0;
          });
          replacement = aggFuncs[funcName](columnValues);
        }
      } else {
        var vals = argNames.map(function (s) {
          if (context.hasOwnProperty(s)) return parseFloat(context[s]) || 0;
          var num = parseFloat(s);
          return isNaN(num) ? 0 : num;
        });
        replacement = aggFuncs[funcName](vals);
      }
      expr = expr.substring(0, funcMatch.index) + replacement + expr.substring(openIdx + argsStr.length + 2);
      funcPattern.lastIndex = 0; // 重置正则位置，处理替换后可能出现的新函数
    }

    // 替换变量为数值：按 key 长度降序，避免短 key 误匹配长 key 的子串
    // 同时处理 ASCII 和 Unicode 字符的边界匹配
    var resolved = expr;
    var contextKeys = Object.keys(context).sort(function (a, b) { return b.length - a.length; });
    contextKeys.forEach(function (key) {
      // 转义正则特殊字符
      var escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      // 使用 (?<![\\w一-鿿]) 和 (?![\\w一-鿿]) 做 Unicode-aware 单词边界匹配
      var unicodes = '一-鿿';
      var re = new RegExp('(?<![\\w' + unicodes + '])' + escaped + '(?![\\w' + unicodes + '])', 'g');
      var val = parseFloat(context[key]);
      resolved = resolved.replace(re, isNaN(val) ? 0 : val);
    });

    // 安全求值：仅允许数字和基本运算符，不依赖 Function()/eval
    var sanitized = resolved.replace(/\s+/g, '');
    if (!/^[0-9+\-*/().]+$/.test(sanitized)) throw new Error('公式包含无效字符');
    // 使用受控表达式求值替代 Function() eval
    var result = _safeArithEval(sanitized);
    if (isNaN(result) || !isFinite(result)) throw new Error('计算结果无效');
    // 数值范围检查，与后端 MAX_ABS_NUMBER 一致
    if (Math.abs(result) > 1000000000000) throw new Error('数值超出范围');
    return result;
  }

  function buildCalcContext(fieldDefs) {
    var context = {};
    fieldDefs.forEach(function (f) {
      var key = f.key;
      if (!key) return;
      var item = document.getElementById('field_' + f.id);
      if (!item) return;
      var input = item.querySelector('.field-input, .field-select, textarea');
      if (f.field_type === 'table') {
        try {
          var dataEl = document.getElementById('table_data_' + f.id);
          var data = JSON.parse((dataEl && dataEl.value) || '[]');
          context[key] = {
            __tableRows: data,
            __tableColumns: (f.columns || []).map(function (col) { return col.key; })
          };
        } catch (e) {}
      } else if (input) {
        var val = parseFloat(input.value);
        context[key] = isNaN(val) ? (input.value || 0) : val;
      }
    });
    return context;
  }

  function recalcField(el) {
    var fid = parseInt(el.id.replace('calc_', ''));
    var formula = el.dataset.formula;
    var decimals = parseInt(el.dataset.decimals || 2);
    var context = buildCalcContext((window.ContractEditor && window.ContractEditor.config.fields) || []);
    try {
      var result = safeEval(formula, context);
      if (typeof result === 'number') { result = result.toFixed(decimals); }
      el.value = result;
      var hiddenInput = document.getElementById('calc_input_' + fid);
      if (hiddenInput) hiddenInput.value = result;
    } catch (e) { el.value = ''; el.placeholder = 'error'; }
  }

  function recalcAllFields() {
    document.querySelectorAll('.calc-result').forEach(function (el) { recalcField(el); });
  }

  function triggerCalc(changedId) {
    var fieldDefs = (window.ContractEditor && window.ContractEditor.config.fields) || [];
    var normalizedChangedId = String(changedId);
    var changedField = fieldDefs.find(function (f) {
      return String(f.id) === normalizedChangedId;
    });
    if (!changedField || !changedField.key) return;
    var changedKey = changedField.key;
    document.querySelectorAll('.calc-result').forEach(function (el) {
      var depends = [];
      try { depends = JSON.parse(el.dataset.depends || '[]'); } catch (e) {}
      if (depends.indexOf(changedKey) >= 0) { recalcField(el); }
    });
  }

  window.ContractFormulaEngine = Object.freeze({
    safeEval: safeEval,
    recalcField: recalcField,
    recalcAllFields: recalcAllFields,
    triggerCalc: triggerCalc,
  });
})();
