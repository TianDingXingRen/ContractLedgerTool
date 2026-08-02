"""统一金额处理：分（整数）与元（Decimal/字符串）之间的转换。

本项目使用整数"分"（minor unit）存储金额以避免浮点误差，
本模块提供统一的转换函数替代各处散落的 Decimal/100 操作。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union


SQLITE_MAX_INTEGER = 2**63 - 1


def to_minor(value: Union[str, float, Decimal, int, None], *, allow_none: bool = True) -> Optional[int]:
    """将金额（元）转换为分（整数），失败抛出 ValueError。

    >>> to_minor('123.45')
    12345
    >>> to_minor('')
    >>> to_minor(None)
    """
    if value is None:
        if allow_none:
            return None
        raise ValueError('金额不能为空')
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
    else:
        raw = str(value).replace(',', '').replace('，', '').strip()
        if not raw:
            if allow_none:
                return None
            raise ValueError('金额不能为空')
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(f'金额格式无效: {raw!r}') from exc
    if not number.is_finite():
        raise ValueError('金额必须是有限数值')
    if number < 0:
        raise ValueError('金额不能为负数')
    try:
        minor = int((number * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError('金额超出可存储范围') from exc
    if minor > SQLITE_MAX_INTEGER:
        raise ValueError('金额超出可存储范围')
    return minor


def from_minor(minor_value: Optional[int], decimal_places: int = 2) -> str:
    """将整数分转换为元的字符串表示。

    >>> from_minor(12345)
    '123.45'
    >>> from_minor(0)
    '0.00'
    >>> from_minor(None)
    ''
    """
    if minor_value is None:
        return ''
    return f'{Decimal(int(minor_value)) / 100:.{decimal_places}f}'


def from_minor_decimal(minor_value: Optional[int]) -> Decimal:
    """将整数分转换为 Decimal 元，用于精确计算。"""
    if minor_value is None:
        return Decimal('0')
    return Decimal(int(minor_value)) / 100


def float_or_none(value: Union[str, float, int, None]) -> Optional[float]:
    """安全地将值转换为 float，失败返回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(',', '').replace('，', ''))
    except (ValueError, TypeError):
        return None
