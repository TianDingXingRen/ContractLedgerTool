"""计算字段公式求值模块

使用 ast.parse 白名单安全求值，支持 + - * / 四则运算和常用聚合。
"""

import ast
import operator
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from utils.constants import FieldType

# ── 安全运算白名单 ──────────────────────────
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_SAFE_FUNCS = {'SUM', 'AVG', 'MAX', 'MIN', 'COUNT'}
MAX_FORMULA_LENGTH = 500
MAX_AST_NODES = 100
MAX_FUNC_ARGS = 100
MAX_LIST_ITEMS = 100
MAX_ABS_NUMBER = Decimal('1000000000000')


class FormulaError(ValueError):
    """公式求值错误"""
    pass


class _EvalVisitor(ast.NodeVisitor):
    """AST 求值访问器"""

    def __init__(self, context):
        self.context = context

    def visit(self, node):
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise FormulaError('公式只允许数字常量')
            return _checked_number(node.value)
        elif isinstance(node, ast.BinOp):
            op = _SAFE_OPS.get(type(node.op))
            if op is None:
                raise FormulaError(f'不支持的运算符: {type(node.op).__name__}')
            left_val = self.visit(node.left)
            right_val = self.visit(node.right)
            try:
                return _checked_number(op(left_val, right_val))
            except ZeroDivisionError:
                raise FormulaError(
                    '除数为零，请检查公式中的分母变量是否为空、为零，'
                    '或常量计算中出现除以零',
                )
        elif isinstance(node, ast.UnaryOp):
            op = _SAFE_OPS.get(type(node.op))
            if op is None:
                raise FormulaError(f'不支持的运算符: {type(node.op).__name__}')
            return _checked_number(op(self.visit(node.operand)))
        elif isinstance(node, ast.Name):
            if node.id in self.context:
                val = self.context[node.id]
                if val is None or val == '':
                    raise FormulaError(f'变量 {node.id} 未设置')
                try:
                    return _checked_number(val)
                except (ValueError, TypeError, InvalidOperation):
                    raise FormulaError(f'变量 {node.id} 的值 "{val}" 不是有效数字')
            raise FormulaError(f'未找到变量: {node.id}')
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else ''
            if func_name not in _SAFE_FUNCS:
                raise FormulaError(f'不支持的函数: {func_name}')
            if node.keywords:
                raise FormulaError('函数不支持关键字参数')
            if len(node.args) > MAX_FUNC_ARGS:
                raise FormulaError('函数参数过多')
            if (len(node.args) == 2
                    and isinstance(node.args[0], ast.Name)
                    and isinstance(node.args[1], ast.Name)):
                table_context = self.context.get(node.args[0].id)
                if isinstance(table_context, dict) and '__table_rows__' in table_context:
                    column_key = node.args[1].id
                    columns = table_context.get('__table_columns__', set())
                    if column_key not in columns:
                        raise FormulaError(f'表格 {node.args[0].id} 中不存在列 {column_key}')
                    return _checked_number(resolve_table_aggregate(
                        table_context.get('__table_rows__', []), column_key, func_name
                    ))
            args = [self.visit(a) for a in node.args]

            if func_name == 'SUM':
                return _checked_number(sum(args))
            elif func_name == 'AVG':
                return _checked_number(sum(args) / len(args) if args else 0)
            elif func_name == 'MAX':
                return max(args) if args else 0
            elif func_name == 'MIN':
                return min(args) if args else 0
            elif func_name == 'COUNT':
                return len(args)
        elif isinstance(node, ast.List):
            if len(node.elts) > MAX_LIST_ITEMS:
                raise FormulaError('列表元素过多')
            return [self.visit(el) for el in node.elts]
        else:
            raise FormulaError(f'不支持的表达式: {type(node).__name__}')


class _ValidateVisitor(ast.NodeVisitor):
    """Validate formula syntax without requiring variable values."""

    def visit_Expression(self, node):
        self.visit(node.body)

    def visit_Constant(self, node):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise FormulaError('公式只允许数字常量')

    def visit_BinOp(self, node):
        if type(node.op) not in _SAFE_OPS:
            raise FormulaError(f'不支持的运算符: {type(node.op).__name__}')
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node):
        if type(node.op) not in _SAFE_OPS:
            raise FormulaError(f'不支持的运算符: {type(node.op).__name__}')
        self.visit(node.operand)

    def visit_Name(self, node):
        return None

    def visit_Call(self, node):
        func_name = node.func.id if isinstance(node.func, ast.Name) else ''
        if func_name not in _SAFE_FUNCS:
            raise FormulaError(f'不支持的函数: {func_name}')
        if node.keywords:
            raise FormulaError('函数不支持关键字参数')
        if len(node.args) > MAX_FUNC_ARGS:
            raise FormulaError('函数参数过多')
        for arg in node.args:
            self.visit(arg)

    def visit_List(self, node):
        if len(node.elts) > MAX_LIST_ITEMS:
            raise FormulaError('列表元素过多')
        for item in node.elts:
            self.visit(item)

    def generic_visit(self, node):
        raise FormulaError(f'不支持的表达式: {type(node).__name__}')


def _checked_number(value):
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise FormulaError('公式结果不是数字')
    if not number.is_finite() or abs(number) > MAX_ABS_NUMBER:
        raise FormulaError('公式数值超出允许范围')
    return number


def _parse_formula(expr):
    text = str(expr or '').strip()
    if len(text) > MAX_FORMULA_LENGTH:
        raise FormulaError('公式过长')
    try:
        tree = ast.parse(text, mode='eval')
    except SyntaxError as e:
        raise FormulaError(f'公式语法错误: {e}')
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise FormulaError('公式过于复杂')
    return tree


def validate_formula(expr):
    if not expr or not str(expr).strip():
        return True
    _ValidateVisitor().visit(_parse_formula(expr))
    return True


def safe_eval_decimal(expr, context=None):
    """安全求值公式表达式

    参数:
        expr: 公式字符串，如 "unit_price * quantity"
        context: 变量值字典，如 {'unit_price': 100, 'quantity': 5}

    返回:
        计算结果 (Decimal)

    示例:
        >>> safe_eval('2 + 3 * 4')
        Decimal('14')
        >>> safe_eval('unit_price * qty', {'unit_price': 100, 'qty': 5})
        Decimal('500')
        >>> safe_eval('SUM(a, b, c)', {'a': 1, 'b': 2, 'c': 3})
        Decimal('6')
    """
    if context is None:
        context = {}

    # 空公式返回 0
    if not expr or not expr.strip():
        return Decimal('0')

    try:
        tree = _parse_formula(expr)
        visitor = _EvalVisitor(context)
        result = visitor.visit(tree)
        return _checked_number(result)
    except FormulaError:
        raise
    except Exception as e:
        raise FormulaError(f'公式求值失败: {e}')


def safe_eval(expr, context=None):
    """安全求值公式表达式，保留历史 float 返回类型。"""
    return float(safe_eval_decimal(expr, context))


def resolve_table_aggregate(rows_data, column_key, func='SUM'):
    """计算表格列的聚合值

    参数:
        rows_data: [{col_key: value}, ...] 表格行数据列表
        column_key: 要聚合的列 key
        func: 聚合函数 SUM/AVG/MAX/MIN/COUNT

    返回:
        聚合结果 (float)
    """
    values = []
    for row in rows_data:
        raw = row.get(column_key, 0)
        try:
            values.append(_checked_number(raw))
        except FormulaError:
            values.append(Decimal('0'))

    if func == 'SUM':
        return sum(values, Decimal('0'))
    elif func == 'AVG':
        return sum(values, Decimal('0')) / len(values) if values else Decimal('0')
    elif func == 'MAX':
        return max(values) if values else Decimal('0')
    elif func == 'MIN':
        return min(values) if values else Decimal('0')
    elif func == 'COUNT':
        return len(values)
    return Decimal('0')


def sort_fields_by_dependency(fields):
    """按依赖关系拓扑排序字段

    返回排序后的字段列表，计算字段在依赖的输入字段之后

    参数:
        fields: 字段定义列表，每个含 key, field_type, formula, depends_on 等
    """
    # 分离输入字段和计算字段
    calc_value = FieldType.CALCULATED.value
    input_fields = [f for f in fields if f.get('field_type') != calc_value]
    calc_fields = [f for f in fields if f.get('field_type') == calc_value]

    # 构建依赖图
    calc_by_key = {f['key']: f for f in fields if f.get('key')}
    table_column_keys = {
        col.get('key')
        for field in fields if field.get('field_type') == FieldType.TABLE
        for col in field.get('columns', []) if col.get('key')
    }
    all_keys = set(calc_by_key) | table_column_keys
    resolved = {f['key'] for f in input_fields if f.get('key')}
    resolved.update(table_column_keys)
    ordered_calcs = []
    remaining = list(calc_fields)

    # 迭代解析
    max_iter = len(calc_fields) * 2
    for _ in range(max_iter):
        if not remaining:
            break
        newly_resolved = []
        still_remaining = []
        for f in remaining:
            deps = _get_calc_deps(f)
            if all(d in resolved for d in deps):
                ordered_calcs.append(f)
                resolved.add(f['key'])
                newly_resolved.append(f['key'])
            else:
                still_remaining.append(f)
        remaining = still_remaining
        if not newly_resolved:
            break  # 无法继续解析

    if remaining:
        problem_parts = []
        for f in remaining:
            deps = _get_calc_deps(f)
            missing = sorted(d for d in deps if d not in all_keys)
            name = f.get('label') or f.get('key') or '未命名字段'
            if missing:
                problem_parts.append(f'{name} 缺少依赖: {", ".join(missing)}')
            else:
                problem_parts.append(f'{name} 存在循环依赖')
        raise FormulaError('；'.join(problem_parts))
    return input_fields + ordered_calcs


def sort_table_columns_by_dependency(columns):
    """Return table columns in a safe calculation order.

    Editable columns retain their original order.  Calculated columns are
    topologically sorted from the names referenced by their formulas.  This
    deliberately does not accept an existing calculated cell value as a
    dependency substitute: every calculated dependency must itself be
    resolved during this pass.
    """
    calc_value = FieldType.CALCULATED.value
    input_columns = [
        column for column in columns
        if column.get('field_type') != calc_value
    ]
    calc_columns = [
        column for column in columns
        if column.get('field_type') == calc_value
    ]
    for column in calc_columns:
        if not column.get('key'):
            raise FormulaError('计算列缺少 key')
        if not str(column.get('formula') or '').strip():
            name = column.get('label') or column.get('key')
            raise FormulaError(f'{name} 缺少公式')
    column_keys = [column.get('key') for column in columns if column.get('key')]
    if len(column_keys) != len(set(column_keys)):
        raise FormulaError('表格列 key 不能重复')
    all_keys = set(column_keys)
    resolved = {
        column.get('key') for column in input_columns if column.get('key')
    }
    ordered_calcs = []
    remaining = list(calc_columns)

    while remaining:
        next_remaining = []
        progressed = False
        for column in remaining:
            dependencies = _get_calc_deps(column, include_declared=False)
            if dependencies <= resolved:
                ordered_calcs.append(column)
                resolved.add(column.get('key'))
                progressed = True
            else:
                next_remaining.append(column)
        remaining = next_remaining
        if not progressed:
            break

    if remaining:
        problem_parts = []
        for column in remaining:
            dependencies = _get_calc_deps(column, include_declared=False)
            missing = sorted(dependencies - all_keys)
            name = column.get('label') or column.get('key') or '未命名列'
            if missing:
                problem_parts.append(f'{name} 缺少依赖: {", ".join(missing)}')
            else:
                problem_parts.append(f'{name} 存在循环依赖')
        raise FormulaError('；'.join(problem_parts))

    return input_columns + ordered_calcs


def _get_calc_deps(field, *, include_declared=True):
    """获取计算字段的依赖列表（单次 AST walk，避免重复解析）"""
    formula = field.get('formula', '')
    deps = set()
    tree = _parse_formula(formula)
    # 单次遍历同时完成：变量提取 + 基础安全校验
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _SAFE_FUNCS:
            deps.add(node.id)
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise FormulaError('公式只允许数字常量')
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in _SAFE_OPS:
                raise FormulaError(f'不支持的运算符: {type(node.op).__name__}')
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in _SAFE_OPS:
                raise FormulaError(f'不支持的运算符: {type(node.op).__name__}')
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else ''
            if func_name not in _SAFE_FUNCS:
                raise FormulaError(f'不支持的函数: {func_name}')
            if node.keywords:
                raise FormulaError('函数不支持关键字参数')
            if len(node.args) > MAX_FUNC_ARGS:
                raise FormulaError('函数参数过多')
        elif isinstance(node, ast.List):
            if len(node.elts) > MAX_LIST_ITEMS:
                raise FormulaError('列表元素过多')
        elif isinstance(node, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                ast.USub, ast.UAdd, ast.Load, ast.Store)):
            pass  # 运算符/上下文节点，由父节点处理
        elif not isinstance(node, (ast.Expression, ast.Name, ast.Module)):
            raise FormulaError(f'不支持的表达式: {type(node).__name__}')
    if include_declared:
        field_deps = field.get('depends_on', [])
        deps.update(field_deps)
    return deps


def format_number(value, decimal_places=2):
    """按财务常用的四舍五入规则格式化数字。"""
    try:
        places = max(0, min(6, int(decimal_places)))
        number = _checked_number(value)
        quantum = Decimal('1').scaleb(-places)
        return float(number.quantize(quantum, rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, InvalidOperation, FormulaError):
        return value


def format_number_text(value, decimal_places=2):
    """按固定小数位返回财务数字文本，保留末尾零。"""
    try:
        places = max(0, min(6, int(decimal_places)))
        number = _checked_number(value)
        quantum = Decimal('1').scaleb(-places)
        rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
        return format(rounded, f'.{places}f')
    except (ValueError, TypeError, InvalidOperation, FormulaError):
        return str(value)


def get_calc_deps(field):
    """获取计算字段的依赖列表（公开接口）"""
    return _get_calc_deps(field)


def make_col_key(label, index):
    """从列标签生成键名"""
    key_map = {
        '产品名称': 'product_name', '产品': 'product_name',
        '数量': 'qty',
        '单价': 'unit_price', '价格': 'unit_price',
        '小计': 'subtotal', '合计': 'subtotal', '金额': 'amount',
        '总价': 'total_price',
        '规格型号': 'spec', '型号': 'spec',
        '单位': 'uom', '计量单位': 'uom',
        '备注': 'remark', '说明': 'note',
        '税率': 'tax_rate',
        '税额': 'tax_amount',
    }
    for kw, key in key_map.items():
        if kw in label:
            base = key
            break
    else:
        base = re.sub(r'[^\w]', '', label)[:15] or f'col_{index}'

    return base
