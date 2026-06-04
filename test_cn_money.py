# -*- coding: utf-8 -*-
import unittest
from utils.cn_money import to_chinese

class ToChineseTests(unittest.TestCase):
    def test_zero(self):
        r = to_chinese(0)
        self.assertIn(chr(38646), r)
        self.assertIn(chr(20803), r)
    def test_integer(self):
        r = to_chinese(123)
        self.assertIn(chr(22777), r)
    def test_with_jiao(self):
        r = to_chinese(123.45)
        self.assertIn(chr(35282), r)
        self.assertIn(chr(20998), r)
    def test_float_input(self):
        r = to_chinese(5.0)
        self.assertIn(chr(20237), r)
    def test_str_input(self):
        r = to_chinese('100.50')
        self.assertIn(chr(22777), r)

if __name__ == '__main__':
    unittest.main()
