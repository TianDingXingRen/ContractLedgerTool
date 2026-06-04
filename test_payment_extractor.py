# -*- coding: utf-8 -*-
import unittest

import payment_extractor


class PaymentExtractorTests(unittest.TestCase):
    def test_ignores_price_summary_and_keeps_payment_schedule(self):
        text = (
            '合同款项 订购产品的合同总价款（含税）小写：人民币425,000.00元，'
            '不含税金额376,106.19元，税额48,893.81元。'
            '结算方式及期限(采用以下第2种方式)：一次总付：人民币425,000.00元，时间：2026-05-30；'
            '分期支付：第1笔：支付合同总额的30%，即人民币127,500.00元，时间：2026-06-03。'
        )

        plans = payment_extractor.extract_payment_plans(
            text,
            contract_amount=425000,
            sign_date='2026-05-19',
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]['ratio'], 30.0)
        self.assertEqual(plans[0]['due_amount'], 127500.0)
        self.assertEqual(plans[0]['due_date'], '2026-06-03')

    def test_ignores_vat_percentage_as_payment_ratio(self):
        text = '验收后30日内提供增值税专用发票，税率13%，税额48,893.81元。'
        plans = payment_extractor.extract_payment_plans(text, contract_amount=425000)
        self.assertEqual(plans, [])


if __name__ == '__main__':
    unittest.main()
