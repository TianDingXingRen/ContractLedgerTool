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
        if (op === '*' || op === '/') { consume(); var right = parseFactor(); if (op === '/' && right === 0) throw new Error('Division by zero'); left = op === '*' ? left * right : left / right; }
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

    expr = expr.replace(/(SUM|AVG|MAX|MIN|COUNT)\(([^)]+)\)/g, function (match, func, args) {
      var vals = args.split(',').map(function (s) {
        s = s.trim();
        if (context.hasOwnProperty(s)) return parseFloat(context[s]) || 0;
        var num = parseFloat(s);
        return isNaN(num) ? 0 : num;
      });
      return aggFuncs[func](vals);
    });

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
    if (!/^[0-9+\-*/().]+$/.test(sanitized)) return 0;
    // 使用受控表达式求值替代 Function() eval
    try {
      var result = _safeArithEval(sanitized);
      return isNaN(result) || !isFinite(result) ? 0 : result;
    } catch (e) { return 0; }
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
          data.forEach(function (row) {
            Object.keys(row).forEach(function (ck) {
              context[key + '.' + ck] = parseFloat(row[ck]) || 0;
            });
          });
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
    var context = buildCalcContext(window.CT_fields || []);
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
    var fieldDefs = window.CT_fields || [];
    var changedField = fieldDefs.find(function (f) { return f.id === changedId; });
    if (!changedField || !changedField.key) return;
    var changedKey = changedField.key;
    document.querySelectorAll('.calc-result').forEach(function (el) {
      var depends = [];
      try { depends = JSON.parse(el.dataset.depends || '[]'); } catch (e) {}
      if (depends.indexOf(changedKey) >= 0) { recalcField(el); }
    });
  }

  window.CT_safeEval = safeEval;
  window.CT_recalcField = recalcField;
  window.CT_recalcAllFields = recalcAllFields;
  window.CT_triggerCalc = triggerCalc;
})();
