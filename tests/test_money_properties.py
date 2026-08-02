from decimal import Decimal
import random

import pytest

from utils.money import from_minor, to_minor


def test_minor_unit_round_trip_for_seeded_value_space():
    rng = random.Random(20260720)
    samples = [0, 1, 99, 100, 10**12]
    samples.extend(rng.randrange(0, 10**12) for _ in range(2_000))

    for minor_value in samples:
        assert to_minor(from_minor(minor_value), allow_none=False) == minor_value


@pytest.mark.parametrize(
    ('yuan', 'expected_minor'),
    [
        ('0.004', 0),
        ('0.005', 1),
        ('1.0049', 100),
        ('1.005', 101),
        ('9999999999.995', 1_000_000_000_000),
    ],
)
def test_money_rounding_is_decimal_half_up(yuan, expected_minor):
    assert to_minor(Decimal(yuan), allow_none=False) == expected_minor


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', float('nan'), float('inf')])
def test_non_finite_money_is_rejected(value):
    with pytest.raises(ValueError, match='有限数值'):
        to_minor(value, allow_none=False)
