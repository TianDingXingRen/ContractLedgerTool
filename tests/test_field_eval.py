# -*- coding: utf-8 -*-
import unittest
import field_eval

class SafeEvalTests(unittest.TestCase):
    def test_simple_addition(self):
        self.assertEqual(field_eval.safe_eval('1 + 2'), 3.0)
    def test_complex_expression(self):
        self.assertEqual(field_eval.safe_eval('2 + 3 * 4'), 14.0)
    def test_parentheses(self):
        self.assertEqual(field_eval.safe_eval('(2 + 3) * 4'), 20.0)
    def test_zero_division_raises(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('1 / 0')
    def test_empty_returns_zero(self):
        self.assertEqual(field_eval.safe_eval(''), 0)
    def test_variable_substitution(self):
        self.assertEqual(field_eval.safe_eval('a + b', {'a': 10, 'b': 20}), 30.0)
    def test_missing_variable_raises(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('missing_var + 1')
    def test_none_variable_raises(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('x * 2', {'x': None})
    def test_overflow_raises(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('1' + '0' * 13)
    def test_negative_number(self):
        self.assertEqual(field_eval.safe_eval('-5 + 3'), -2.0)

class AggregateFunctionTests(unittest.TestCase):
    def test_sum(self):
        self.assertEqual(field_eval.safe_eval('SUM(1, 2, 3)'), 6.0)
    def test_avg(self):
        self.assertEqual(field_eval.safe_eval('AVG(10, 20, 30)'), 20.0)
    def test_max_min_count(self):
        self.assertEqual(field_eval.safe_eval('MAX(5,3,9)'), 9.0)
        self.assertEqual(field_eval.safe_eval('MIN(5,3,9)'), 3.0)
        self.assertEqual(field_eval.safe_eval('COUNT(1,2,3)'), 3.0)
    def test_unknown_function_raises(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.safe_eval('POW(2, 3)')

class ValidateFormulaTests(unittest.TestCase):
    def test_valid_formula(self):
        self.assertTrue(field_eval.validate_formula('a + b * 2'))
    def test_power_rejected(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.validate_formula('9 ** 9')
    def test_comparison_rejected(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.validate_formula('a > b')
    def test_string_constant_rejected(self):
        with self.assertRaises(field_eval.FormulaError):
            field_eval.validate_formula(chr(34) + 'hello' + chr(34))
    def test_empty_pass(self):
        self.assertTrue(field_eval.validate_formula(''))

class SortByDependencyTests(unittest.TestCase):
    def test_no_calculated(self):
        fields = [{'key': 'a', 'label': 'A', 'field_type': 'text'}, {'key': 'b', 'label': 'B', 'field_type': 'text'}]
        result = field_eval.sort_fields_by_dependency(fields)
        self.assertEqual([f['key'] for f in result], ['a', 'b'])
    def test_simple_ordering(self):
        fields = [
            {'key': 'sum', 'label': 'Sum', 'field_type': 'calculated', 'formula': 'a + b'},
            {'key': 'a', 'label': 'A', 'field_type': 'text'},
            {'key': 'b', 'label': 'B', 'field_type': 'text'},
        ]
        result = field_eval.sort_fields_by_dependency(fields)
        keys = [f['key'] for f in result]
        self.assertLess(keys.index('a'), keys.index('sum'))
        self.assertLess(keys.index('b'), keys.index('sum'))
    def test_circular_raises(self):
        fields = [{'key': 'a', 'label': 'A', 'field_type': 'calculated', 'formula': 'b'},
                  {'key': 'b', 'label': 'B', 'field_type': 'calculated', 'formula': 'a'}]
        with self.assertRaises(field_eval.FormulaError):
            field_eval.sort_fields_by_dependency(fields)
    def test_missing_dependency_with_name(self):
        fields = [{'key': 'total', 'label': 'my_total', 'field_type': 'calculated', 'formula': 'qty * price'}]
        with self.assertRaises(field_eval.FormulaError) as cm:
            field_eval.sort_fields_by_dependency(fields)
        self.assertIn('my_total', str(cm.exception))

class ResolveTableAggregateTests(unittest.TestCase):
    def test_sum(self):
        self.assertEqual(field_eval.resolve_table_aggregate([{'v': 100}, {'v': 200}], 'v', 'SUM'), 300)
    def test_empty(self):
        self.assertEqual(field_eval.resolve_table_aggregate([], 'v', 'SUM'), 0)
    def test_string_values(self):
        self.assertEqual(field_eval.resolve_table_aggregate([{'v': '100.5'}, {'v': '200.25'}], 'v', 'SUM'), 300.75)

class FormatNumberTests(unittest.TestCase):
    def test_round(self):
        self.assertEqual(field_eval.format_number(3.14159, 2), 3.14)
    def test_invalid(self):
        self.assertEqual(field_eval.format_number('abc', 2), 'abc')

class MakeColKeyTests(unittest.TestCase):
    def test_known(self):
        self.assertEqual(field_eval.make_col_key('产品名称', 0), 'product_name')
        self.assertEqual(field_eval.make_col_key('数量', 1), 'qty')
        # Unknown Chinese label falls back to index-based name
        key = field_eval.make_col_key('未知列', 0)
        self.assertTrue(key.startswith('col_') or '未知列' in key)

class GetCalcDepsTests(unittest.TestCase):
    def test_extracts(self):
        deps = field_eval.get_calc_deps({'formula': 'a + b * c'})
        self.assertEqual(deps, {'a', 'b', 'c'})

class FormulaEdgeCaseTests(unittest.TestCase):
    def test_negative_result(self):
        self.assertEqual(field_eval.safe_eval('5 - 10'), -5.0)
    def test_unary_positive(self):
        self.assertEqual(field_eval.safe_eval('+5'), 5.0)
    def test_nested_negation(self):
        self.assertEqual(field_eval.safe_eval('--5'), 5.0)

if __name__ == '__main__':
    unittest.main()
