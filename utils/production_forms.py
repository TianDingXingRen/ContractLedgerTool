"""Framework-neutral parsing for contract items and production notices."""

from __future__ import annotations

from utils.field_utils import normalize_date


MAX_ITEM_ROWS = 500


def _normalized_date(value, label, *, required=False):
    raw = str(value or '').strip()
    if not raw and not required:
        return ''
    normalized = normalize_date(raw)
    if not normalized:
        raise ValueError(f'{label}格式无效，请使用 YYYY-MM-DD')
    return normalized


def contract_item_rows(form):
    try:
        count = min(
            MAX_ITEM_ROWS, max(0, int(form.get('item_count', 0)))
        )
    except (TypeError, ValueError) as exc:
        raise ValueError('合同产品行数无效') from exc
    return [
        {
            'id': form.get(f'item_{index}_id', ''),
            'line_no': form.get(
                f'item_{index}_line_no', index + 1
            ),
            'item_code': form.get(
                f'item_{index}_item_code', ''
            ),
            'item_name': form.get(
                f'item_{index}_item_name', ''
            ),
            'spec_model': form.get(
                f'item_{index}_spec_model', ''
            ),
            'drawing_no': form.get(
                f'item_{index}_drawing_no', ''
            ),
            'contracted_qty': form.get(
                f'item_{index}_contracted_qty', ''
            ),
            'unit': form.get(f'item_{index}_unit', '个'),
            'unit_price': form.get(
                f'item_{index}_unit_price', ''
            ),
            'serial_start': form.get(
                f'item_{index}_serial_start', ''
            ),
            'serial_end': form.get(
                f'item_{index}_serial_end', ''
            ),
            'delete': form.get(f'item_{index}_delete') == '1',
        }
        for index in range(count)
    ]


def production_notice_rows(form):
    try:
        count = min(
            MAX_ITEM_ROWS, max(0, int(form.get('item_count', 0)))
        )
    except (TypeError, ValueError) as exc:
        raise ValueError('投产通知产品行数无效') from exc

    rows = []
    for index in range(count):
        delivery_raw = str(
            form.get(
                f'item_{index}_required_delivery_date', ''
            )
            or ''
        ).strip()
        rows.append(
            {
                'contract_item_id': form.get(
                    f'item_{index}_contract_item_id', ''
                ),
                'notice_qty': form.get(
                    f'item_{index}_notice_qty', ''
                ),
                'serial_start': form.get(
                    f'item_{index}_serial_start', ''
                ),
                'serial_end': form.get(
                    f'item_{index}_serial_end', ''
                ),
                'required_delivery_date': (
                    _normalized_date(
                        delivery_raw, '要求交付日期'
                    )
                    if delivery_raw
                    else ''
                ),
                'remark': form.get(
                    f'item_{index}_remark', ''
                ),
            }
        )
    return rows


def production_notice_header(form):
    notice_date_raw = str(
        form.get('notice_date', '') or ''
    ).strip()
    return {
        'notice_no': form.get('notice_no', ''),
        'notice_date': (
            _normalized_date(notice_date_raw, '通知日期')
            if notice_date_raw
            else ''
        ),
        'supplier_name': form.get('supplier_name', ''),
        'project_name': form.get('project_name', ''),
        'remark': form.get('remark', ''),
        'operator': form.get('operator', ''),
    }
