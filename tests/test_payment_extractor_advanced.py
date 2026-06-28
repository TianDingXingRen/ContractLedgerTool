# -*- coding: utf-8 -*-
"""Advanced tests for payment_extractor: edge cases, ReDoS safety, Chinese numbers."""
import time
import unittest

import payment_extractor


class AmountExtractionTests(unittest.TestCase):
    """_extract_amounts 金额提取边界测试"""

    def test_normal_rmb(self):
        result = payment_extractor._extract_amounts('人民币1,234.56元')
        self.assertEqual(result, [1234.56])

    def test_wan_unit(self):
        result = payment_extractor._extract_amounts('￥500万元')
        self.assertEqual(result, [5000000.0])

    def test_rmb_english_prefix(self):
        result = payment_extractor._extract_amounts('RMB 100.00 元')
        self.assertEqual(result, [100.0])

    def test_multiple_amounts(self):
        result = payment_extractor._extract_amounts('首付100元，尾款200元')
        self.assertEqual(result, [100.0, 200.0])

    def test_no_amount_unit_no_match(self):
        result = payment_extractor._extract_amounts('金额500')
        self.assertEqual(result, [])

    def test_overflow_20_digit_rejected(self):
        result = payment_extractor._extract_amounts('人民币' + '1' * 20 + '元')
        self.assertEqual(result, [])

    def test_overflow_500_digit_rejected(self):
        result = payment_extractor._extract_amounts('人民币' + '9' * 500 + '元')
        self.assertEqual(result, [])

    def test_15_digit_still_accepted(self):
        result = payment_extractor._extract_amounts('人民币999999999999999元')
        self.assertEqual(result, [999999999999999.0])

    def test_empty_text(self):
        result = payment_extractor._extract_amounts('')
        self.assertEqual(result, [])


class RatioExtractionTests(unittest.TestCase):
    """_extract_ratios 比例提取测试"""

    def test_simple_percent(self):
        result = payment_extractor._extract_ratios('支付30%')
        self.assertEqual(result, [30.0])

    def test_cn_percent_fifty(self):
        result = payment_extractor._extract_ratios('百分之五十')
        self.assertEqual(result, [50.0])

    def test_cn_percent_hundred(self):
        result = payment_extractor._extract_ratios('百分之百')
        self.assertEqual(result, [100.0])

    def test_vat_rate_excluded(self):
        result = payment_extractor._extract_ratios('增值税率13%税额')
        self.assertEqual(result, [])

    def test_tax_rate_excluded(self):
        result = payment_extractor._extract_ratios('税率6%')
        self.assertEqual(result, [])

    def test_multiple_ratios(self):
        result = payment_extractor._extract_ratios('30%，验收后支付70%')
        self.assertEqual(result, [30.0, 70.0])


class ChineseNumberTests(unittest.TestCase):
    """_parse_cn_number 中文数字解析测试"""

    def test_pure_digits(self):
        self.assertEqual(payment_extractor._parse_cn_number('123'), 123.0)

    def test_single_ten(self):
        self.assertEqual(payment_extractor._parse_cn_number('十'), 10.0)

    def test_twenty(self):
        self.assertEqual(payment_extractor._parse_cn_number('二十'), 20.0)

    def test_thirty_five(self):
        self.assertEqual(payment_extractor._parse_cn_number('三十五'), 35.0)

    def test_hundred(self):
        self.assertEqual(payment_extractor._parse_cn_number('一百'), 100.0)

    def test_120(self):
        self.assertEqual(payment_extractor._parse_cn_number('一百二十'), 120.0)

    def test_123(self):
        self.assertEqual(payment_extractor._parse_cn_number('一百二十三'), 123.0)

    def test_3000(self):
        self.assertEqual(payment_extractor._parse_cn_number('三千'), 3000.0)

    def test_5600(self):
        self.assertEqual(payment_extractor._parse_cn_number('五千六百'), 5600.0)

    def test_10000(self):
        self.assertEqual(payment_extractor._parse_cn_number('一万'), 10000.0)

    def test_50000(self):
        self.assertEqual(payment_extractor._parse_cn_number('五万'), 50000.0)

    def test_53000(self):
        self.assertEqual(payment_extractor._parse_cn_number('五万三千'), 53000.0)

    def test_120000(self):
        self.assertEqual(payment_extractor._parse_cn_number('一十二万'), 120000.0)

    def test_1200000(self):
        self.assertEqual(payment_extractor._parse_cn_number('一百二十万'), 1200000.0)

    def test_100_million(self):
        self.assertEqual(payment_extractor._parse_cn_number('一亿'), 100000000.0)

    def test_120_million(self):
        self.assertEqual(payment_extractor._parse_cn_number('一亿二千万'), 120000000.0)

    def test_205_with_zero(self):
        self.assertEqual(payment_extractor._parse_cn_number('二百零五'), 205.0)

    def test_1010_with_zero(self):
        self.assertEqual(payment_extractor._parse_cn_number('一千零一十'), 1010.0)

    def test_350_million(self):
        self.assertEqual(payment_extractor._parse_cn_number('三亿五千万'), 350000000.0)

    def test_invalid_returns_none(self):
        self.assertIsNone(payment_extractor._parse_cn_number('abc'))

    def test_empty_returns_none(self):
        self.assertIsNone(payment_extractor._parse_cn_number(''))

    def test_liang_as_two(self):
        self.assertEqual(payment_extractor._parse_cn_number('两千'), 2000.0)


class ReDoSSafetyTests(unittest.TestCase):
    """正则安全性测试：确保恶意输入不会导致超时"""

    def test_1000_digits_fast(self):
        start = time.time()
        payment_extractor._extract_amounts('人民币' + '1' * 1000 + '元')
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f'Too slow: {elapsed:.3f}s')

    def test_1000_ten_chars_fast(self):
        start = time.time()
        payment_extractor._extract_ratios('百分之' + '十' * 1000)
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f'Too slow: {elapsed:.3f}s')

    def test_long_condition_clause_fast(self):
        text = '在合同签订后' + '个' * 500 + '工作日内支付30%'
        start = time.time()
        payment_extractor.extract_payment_plans(text)
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f'Too slow: {elapsed:.3f}s')


class SegmentParsingTests(unittest.TestCase):
    """_parse_segment 条款解析测试"""

    def test_conditional_two_phases(self):
        text = '签订后30日内支付30%，验收后支付70%'
        plans = payment_extractor.extract_payment_plans(text, contract_amount=100000)
        self.assertEqual(len(plans), 2)

    def test_fixed_date_payment(self):
        text = '2025-01-15前支付全部款项50000元'
        plans = payment_extractor.extract_payment_plans(text, contract_amount=50000)
        self.assertGreaterEqual(len(plans), 1)
        self.assertEqual(plans[0]['due_date'], '2025-01-15')

    def test_warranty_phase_preserved(self):
        text = '质保金5%，质保期满后支付'
        plans = payment_extractor.extract_payment_plans(text, contract_amount=100000)
        self.assertGreaterEqual(len(plans), 1)

    def test_trim_excludes_price_summary(self):
        text = '合同总价款人民币425,000.00元。结算方式：分期支付：30%即127,500元。'
        plans = payment_extractor.extract_payment_plans(text, contract_amount=425000)
        for plan in plans:
            self.assertNotIn('总价款', plan.get('source_text', ''))

    def test_empty_text_no_plans(self):
        plans = payment_extractor.extract_payment_plans('')
        self.assertEqual(plans, [])

    def test_no_payment_clause_no_plans(self):
        plans = payment_extractor.extract_payment_plans('本合同一式两份，双方各执一份。')
        self.assertEqual(plans, [])


if __name__ == '__main__':
    unittest.main()
