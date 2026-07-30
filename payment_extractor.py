"""Compatibility facade for the deterministic payment extraction pipeline.

Implementation lives in ``payment_extraction.tokenizer``,
``payment_extraction.parser`` and ``payment_extraction.resolver``.  The
historical module-level API remains available while callers migrate to the
stage that owns each operation.
"""

from __future__ import annotations

from payment_extraction.parser import (
    EVENT_LABELS,
    EVENT_PATTERNS,
    REPEAT_KEYWORDS,
    condition_label as _condition_label,
    condition_logic as _condition_logic,
    detect_conditions as _detect_conditions,
    detect_event as _detect_event,
    is_recurring as _is_recurring,
    phase_name as _phase_name,
    scope_for_rule as _scope_for_rule,
)
from payment_extraction.resolver import (
    EXTRACTOR_VERSION,
    MAX_EXTRACTED_PLANS,
    MAX_EXTRACTED_RULES,
    PaymentExtractionResult,
    add_days as _add_days,
    amounts_conflict as _amounts_conflict,
    block_label as _block_label,
    calculated_amount_for as _calculated_amount,
    confidence as _confidence,
    dedupe_plans as _dedupe_plans,
    dedupe_rules as _dedupe_rules,
    fingerprint as _fingerprint,
    make_plan as _make_plan,
    paired_amount as _paired_amount,
    parse_segment as _parse_segment,
    parse_status as _parse_status,
    propagate_group_context as _propagate_group_context,
    resolve_rule as _parse_rule,
    safe_float as _safe_float,
    status_confidence as _status_confidence,
    sync_plan_status as _sync_plan_status,
    trim_plans as _trim_plans,
    validate_rule_groups as _validate_rule_groups,
)
from payment_extraction.tokenizer import (
    ACTION_PATTERN,
    AMOUNT_BASIS_PATTERNS,
    EXCLUDE_PAYMENT_KEYWORDS,
    GENERIC_SECTION_HEADING,
    NUMBERED_BOUNDARY,
    PAYMENT_ACTION_KEYWORDS,
    PAYMENT_KEYWORDS,
    PAYMENT_SECTION_HEADING,
    PLANISH_NO_MONEY_KEYWORDS,
    PRICE_SUMMARY_KEYWORDS,
    STRONG_PAYMENT_KEYWORDS,
    TRIGGER_ONLY_KEYWORDS,
    action_matches as _action_matches,
    coerce_blocks as _coerce_blocks,
    detect_amount_basis as _detect_amount_basis,
    extract_amounts as _extract_amounts,
    extract_date as _extract_date,
    extract_days as _extract_days,
    extract_docx_blocks,
    extract_docx_text,
    extract_ratios as _extract_ratios,
    is_candidate_clause as _is_candidate_clause,
    looks_like_price_summary as _looks_like_price_summary,
    mark_payment_context as _mark_payment_context,
    parse_cn_number as _parse_cn_number,
    payment_snippets as _payment_snippets,
    selected_payment_option as _selected_payment_option,
    split_segments as _split_segments,
)


def extract_payment_plans(text, contract_amount=None, sign_date=''):
    """Compatibility API returning only actionable one-off plan drafts."""
    return extract_payment_items(text, contract_amount, sign_date).plans


def extract_payment_items(source, contract_amount=None, sign_date=''):
    """Extract versioned contractual rules and resolvable payment plans."""
    blocks = _mark_payment_context(_coerce_blocks(source))
    full_text = '\n'.join(block['text'] for block in blocks)
    selected_option = _selected_payment_option(full_text)
    rules = []
    plans = []
    warnings = []

    for block in blocks:
        snippets = _payment_snippets(
            block['text'],
            payment_context=bool(block.get('payment_context')),
        )
        for snippet in snippets:
            if selected_option == 2 and any(
                keyword in snippet
                for keyword in ('一次性总付', '一次总付', '一次付清')
            ):
                continue
            if selected_option == 1 and '分期支付' in snippet:
                continue
            group_key = _fingerprint(
                f"{block.get('kind')}|"
                f"{block.get('index', block.get('row_index', 0))}|"
                f'{snippet}'
            )
            for segment_index, segment in enumerate(
                _split_segments(snippet)
            ):
                parsed_rules, draft_plans = _parse_rule(
                    segment,
                    contract_amount=contract_amount,
                    sign_date=sign_date,
                    group_key=group_key,
                    ordinal=segment_index,
                    block=block,
                )
                rules.extend(parsed_rules)
                plans.extend(draft_plans)

    rules = _propagate_group_context(_dedupe_rules(rules))
    rules = _validate_rule_groups(rules)[:MAX_EXTRACTED_RULES]
    rule_by_fingerprint = {
        rule['rule_fingerprint']: rule
        for rule in rules
    }
    for plan in plans:
        rule = rule_by_fingerprint.get(plan.get('rule_fingerprint'))
        if rule:
            _sync_plan_status(plan, rule)
    plans = [
        plan
        for plan in plans
        if (
            rule_by_fingerprint.get(plan.get('rule_fingerprint'))
            or {}
        ).get('repeat_mode') != 'each_event'
    ]
    plans = _trim_plans(
        _dedupe_plans(plans), contract_amount
    )[:MAX_EXTRACTED_PLANS]
    if len(rules) >= MAX_EXTRACTED_RULES:
        warnings.append('付款规则数量达到安全上限，请人工核对合同结构')
    return PaymentExtractionResult(
        plans=plans,
        rules=rules,
        warnings=warnings,
    )


__all__ = [
    'ACTION_PATTERN',
    'AMOUNT_BASIS_PATTERNS',
    'EVENT_LABELS',
    'EVENT_PATTERNS',
    'EXCLUDE_PAYMENT_KEYWORDS',
    'EXTRACTOR_VERSION',
    'GENERIC_SECTION_HEADING',
    'NUMBERED_BOUNDARY',
    'PAYMENT_ACTION_KEYWORDS',
    'PAYMENT_KEYWORDS',
    'PAYMENT_SECTION_HEADING',
    'PLANISH_NO_MONEY_KEYWORDS',
    'PRICE_SUMMARY_KEYWORDS',
    'PaymentExtractionResult',
    'REPEAT_KEYWORDS',
    'STRONG_PAYMENT_KEYWORDS',
    'TRIGGER_ONLY_KEYWORDS',
    '_action_matches',
    '_add_days',
    '_amounts_conflict',
    '_block_label',
    '_calculated_amount',
    '_condition_label',
    '_condition_logic',
    '_confidence',
    '_detect_amount_basis',
    '_detect_conditions',
    '_detect_event',
    '_extract_amounts',
    '_extract_date',
    '_extract_days',
    '_extract_ratios',
    '_fingerprint',
    '_is_candidate_clause',
    '_is_recurring',
    '_looks_like_price_summary',
    '_make_plan',
    '_paired_amount',
    '_parse_cn_number',
    '_parse_rule',
    '_parse_segment',
    '_parse_status',
    '_phase_name',
    '_safe_float',
    '_scope_for_rule',
    '_status_confidence',
    'extract_docx_blocks',
    'extract_docx_text',
    'extract_payment_items',
    'extract_payment_plans',
]
