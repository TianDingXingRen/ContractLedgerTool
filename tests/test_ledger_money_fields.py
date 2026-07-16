import pytest

from ledger_store import money_fields


def test_amount_pair_rounds_once_into_authoritative_minor_units():
    assert money_fields.amount_pair('1,234.565') == (123457, 1234.57)
    assert money_fields.amount_pair('') == (None, None)


def test_public_amounts_prefer_minor_columns_over_legacy_real_values():
    row = money_fields.with_public_amounts({
        'amount': 99.99,
        'amount_minor': 29,
        'paid_amount': 88.88,
        'paid_amount_minor': 10,
    })

    assert row['amount'] == 0.29
    assert row['paid_amount'] == 0.10


@pytest.mark.parametrize(
    ('paid_amount', 'paid_date', 'expected_status'),
    [
        ('0', '', 'unpaid'),
        ('1.01', '2026-07-15', 'partial'),
        ('10.29', '2026-07-15', 'paid'),
    ],
)
def test_payment_status_is_derived_from_minor_units(
    paid_amount, paid_date, expected_status
):
    row = money_fields.normalize_payment_consistency({
        'due_amount': '10.29',
        'paid_amount': paid_amount,
        'paid_date': paid_date,
    })

    assert row['due_amount_minor'] == 1029
    assert row['payment_status'] == expected_status


def test_paid_amount_requires_date_and_cannot_exceed_due_amount():
    with pytest.raises(ValueError, match='必须填写实付日期'):
        money_fields.normalize_payment_consistency({
            'due_amount': 10,
            'paid_amount': 1,
        })

    with pytest.raises(ValueError, match='不能大于应付金额'):
        money_fields.normalize_payment_consistency({
            'due_amount': 10,
            'paid_amount': 11,
            'paid_date': '2026-07-15',
        })


def test_plan_assignment_keeps_legacy_and_minor_columns_together():
    assignments = []
    values = []

    money_fields.append_plan_assignment(
        assignments,
        values,
        'due_amount',
        {'due_amount': 0.29, 'due_amount_minor': 29},
    )

    assert assignments == ['due_amount = ?', 'due_amount_minor = ?']
    assert values == [0.29, 29]
