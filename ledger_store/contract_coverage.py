"""Coverage normalization for newly created contract ledger rows."""


def normalize_new_contract_coverage(summary):
    """Validate and normalize coverage values for a new ledger row.

    Form-driven creation always supplies ``coverage_mode``. A missing mode is
    retained only for lower-level legacy callers, where two empty endpoints
    represent the historical ``pending`` state.
    """
    mode = str(summary.get('coverage_mode') or '').strip()
    if mode and mode not in {'range', 'not_applicable'}:
        raise ValueError('发次适用方式无效')

    raw_flag = summary.get('coverage_not_applicable')
    if raw_flag is None:
        coverage_not_applicable = 1 if mode == 'not_applicable' else 0
    elif raw_flag in (True, 1, '1'):
        coverage_not_applicable = 1
    elif raw_flag in (False, 0, '0', ''):
        coverage_not_applicable = 0
    else:
        raise ValueError('发次适用状态无效')

    if mode and coverage_not_applicable != (mode == 'not_applicable'):
        raise ValueError('发次适用方式与状态不一致')

    coverage_start = summary.get('coverage_start')
    coverage_end = summary.get('coverage_end')
    if coverage_start == '':
        coverage_start = None
    if coverage_end == '':
        coverage_end = None
    if (coverage_start is None) != (coverage_end is None):
        raise ValueError('起始发次和结束发次需要同时填写')
    if coverage_not_applicable:
        if coverage_start is not None or coverage_end is not None:
            raise ValueError('发次不适用时不能填写起始发次或结束发次')
        return 1, None, None

    if mode == 'range' and coverage_start is None:
        raise ValueError('请选择并填写起始发次和结束发次')
    if coverage_start is not None:
        try:
            normalized_start = int(coverage_start)
            normalized_end = int(coverage_end)
        except (TypeError, ValueError) as exc:
            raise ValueError('起始发次和结束发次必须是整数') from exc
        if (
            isinstance(coverage_start, bool)
            or isinstance(coverage_end, bool)
            or str(normalized_start) != str(coverage_start).strip()
            or str(normalized_end) != str(coverage_end).strip()
            or not 1 <= normalized_start <= 1_000_000_000
            or not 1 <= normalized_end <= 1_000_000_000
        ):
            raise ValueError('起始发次和结束发次必须是1到1000000000之间的整数')
        coverage_start = normalized_start
        coverage_end = normalized_end
        if coverage_start > coverage_end:
            raise ValueError('起始发次不能大于结束发次')
        if not str(summary.get('project_name') or '').strip():
            raise ValueError('填写发次范围前，请先填写项目名称')
    return 0, coverage_start, coverage_end
