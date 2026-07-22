import payment_extractor
import ledger_store


def test_multi_action_clause_binds_each_ratio_to_its_local_conditions():
    result = payment_extractor.extract_payment_items(
        '合同签订后5日内支付30%，到货验收合格且收到发票后10日内支付60%，'
        '剩余10%作为质保金，质保期满后30日内支付。',
        contract_amount=100_000,
        sign_date='2026-07-01',
    )

    assert [rule['ratio'] for rule in result.rules] == [30.0, 60.0, 10.0]
    assert result.rules[0]['trigger_event'] == '合同签订'
    assert result.rules[1]['trigger_event'] == '到货且验收合格且收到发票'
    assert result.rules[1]['condition_logic'] == 'AND'
    assert result.rules[2]['trigger_event'] == '质保期满'
    assert [plan['due_amount'] for plan in result.plans] == [30_000, 60_000, 10_000]


def test_explicit_amount_conflict_is_a_rule_not_an_actionable_plan():
    result = payment_extractor.extract_payment_items(
        '验收合格后支付合同总价的30%，即人民币12万元。',
        contract_amount=500_000,
    )

    assert result.plans == []
    assert len(result.rules) == 1
    rule = result.rules[0]
    assert rule['parse_status'] == 'conflict'
    assert rule['explicit_amount'] == 120_000
    assert rule['calculated_amount'] == 150_000
    assert 'EXPLICIT_AMOUNT_MISMATCH' in rule['reason_codes']


def test_production_notice_group_stays_recurring_and_uses_notice_total():
    result = payment_extractor.extract_payment_items(
        '每次投产通知下达后，按该投产通知内产品总价支付30%，'
        '该批产品到货后支付60%，验收合格后支付10%。',
        contract_amount=1_000_000,
    )

    assert result.plans == []
    assert len(result.rules) == 3
    assert all(rule['repeat_mode'] == 'each_event' for rule in result.rules)
    assert all(rule['scope'] == 'production_notice' for rule in result.rules)
    assert all(
        rule['amount_basis'] == 'production_notice_total'
        for rule in result.rules
    )


def test_recurring_rule_creates_one_idempotent_event_instance(tmp_db):
    extraction = payment_extractor.extract_payment_items(
        '每次投产通知下达后，支付该投产通知内产品总价的30%。'
    )
    contract_id, plan_count = ledger_store.create_contract_with_plans(
        {'title': '动态付款合同'}, {}, '/dynamic.docx', extraction.plans,
        rules=extraction.rules,
    )
    assert plan_count == 0
    rules = ledger_store.list_payment_rules(contract_id)
    assert len(rules) == 1
    rule = rules[0]
    assert rule['repeat_mode'] == 'each_event'
    assert rule['parse_status'] == 'exact'

    ledger_store.set_payment_rule_confirm_status(
        rule['id'], contract_id, 'confirmed'
    )
    first_id, first_created = ledger_store.create_payment_rule_event_instance(
        contract_id,
        rule['id'],
        'TC-001',
        event_date='2026-07-22',
        base_amount=1_000_000,
        reference_name='第一批投产',
    )
    second_id, second_created = ledger_store.create_payment_rule_event_instance(
        contract_id,
        rule['id'],
        'TC-001',
        event_date='2026-07-22',
        base_amount=1_000_000,
        reference_name='第一批投产',
    )

    assert first_created is True
    assert second_created is False
    assert second_id == first_id
    plans = ledger_store.list_payment_plans(contract_id=contract_id)
    assert len(plans) == 1
    assert plans[0]['calculation_base'] == 1_000_000
    assert plans[0]['due_amount'] == 300_000
    assert plans[0]['payment_rule_id'] == rule['id']
    assert len(ledger_store.list_payment_trigger_events(contract_id)) == 1


def test_contract_detail_separates_rules_from_payment_instances(client):
    extraction = payment_extractor.extract_payment_items(
        '每次投产通知下达后，支付该投产通知内产品总价的30%。'
    )
    contract_id, _ = ledger_store.create_contract_with_plans(
        {'title': '投产付款合同'}, {}, '/dynamic.docx', [],
        rules=extraction.rules,
    )

    response = client.get(f'/contracts/{contract_id}?tab=payments')

    assert response.status_code == 200
    assert '合同付款规则'.encode() in response.data
    assert '实际付款计划'.encode() in response.data
    assert '重复触发'.encode() in response.data
    assert '本次投产通知产品总价'.encode() in response.data

    overview = client.get(f'/contracts/{contract_id}')
    assert overview.status_code == 200
    assert '合同信息'.encode() in overview.data
    assert 'data-testid="payment-plan-table"'.encode() not in overview.data
