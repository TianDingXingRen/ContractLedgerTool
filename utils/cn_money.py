"""中文大写金额工具函数"""

from decimal import Decimal, ROUND_HALF_UP

_CN_DIGITS = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
_CN_UNITS = ['', '拾', '佰', '仟']
_CN_SECTIONS = ['', '万', '亿', '万亿']


def to_chinese(value) -> str:
    """阿拉伯数字金额转中文大写（元角分），接受 Decimal/float/int/str"""
    if isinstance(value, (int, float)):
        value = Decimal(str(value))
    elif isinstance(value, str):
        value = Decimal(value)
    value = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    text = str(value)
    if '.' not in text:
        text += '.00'
    int_part, dec_part = text.split('.')
    dec_part = (dec_part + '00')[:2]

    result = ''
    if int_part == '0':
        result = '零'
    else:
        int_str = int_part
        sections = []
        while int_str:
            sections.insert(0, int_str[-4:])
            int_str = int_str[:-4]

        for si, sec in enumerate(sections):
            sec_num = int(sec)
            if sec_num == 0:
                if result and si < len(sections) - 1:
                    if not result.endswith('零'):
                        result += '零'
                continue
            sec_text = ''
            for i, ch in enumerate(sec[::-1]):
                digit = int(ch)
                pos = i
                if digit == 0:
                    if sec_text and not sec_text.startswith('零'):
                        sec_text = '零' + sec_text
                else:
                    sec_text = _CN_DIGITS[digit] + _CN_UNITS[pos] + sec_text
            unit = _CN_SECTIONS[len(sections) - 1 - si]
            result += sec_text + unit

    result += '元'
    jiao = int(dec_part[0])
    fen = int(dec_part[1])
    if jiao == 0 and fen == 0:
        result += '整'
    else:
        if jiao > 0:
            result += _CN_DIGITS[jiao] + '角'
        if fen > 0:
            result += _CN_DIGITS[fen] + '分'
    return result
