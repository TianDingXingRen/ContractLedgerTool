"""Compatibility contracts for route-slimming refactors."""


PAYMENT_AND_PRODUCTION_ROUTES = {
    (
        'payments.api_payments_due_soon',
        '/api/payments/due-soon',
        ('GET',),
    ),
    (
        'payments.contract_serials_bulk_amount',
        '/contracts/<int:contract_id>/serials/bulk-amount',
        ('POST',),
    ),
    (
        'payments.contract_serials_save',
        '/contracts/<int:contract_id>/serials/save',
        ('POST',),
    ),
    (
        'payments.contract_serials_sync',
        '/contracts/<int:contract_id>/serials/sync',
        ('POST',),
    ),
    (
        'payments.export_next_month_payments',
        '/payment-plans/export-next-month',
        ('POST',),
    ),
    (
        'payments.export_payment_plans',
        '/payment-plans/export',
        ('POST',),
    ),
    (
        'payments.payment_plan_list',
        '/payment-plans',
        ('GET',),
    ),
    (
        'payments.payment_plan_quick_update',
        '/payment-plans/<int:plan_id>/quick-update',
        ('POST',),
    ),
    (
        'payments.payment_plans_batch_confirm',
        '/payment-plans/batch-confirm',
        ('POST',),
    ),
    (
        'payments.payment_plans_batch_paid',
        '/payment-plans/batch-paid',
        ('POST',),
    ),
    (
        'payments.payment_plans_confirm_all',
        '/contracts/<int:contract_id>/payments/confirm-all',
        ('POST',),
    ),
    (
        'payments.payment_plans_save',
        '/contracts/<int:contract_id>/payments/save',
        ('POST',),
    ),
    (
        'payments.payment_rule_edit',
        '/contracts/<int:contract_id>/payment-rules/<int:rule_id>/edit',
        ('POST',),
    ),
    (
        'payments.payment_rule_status',
        '/contracts/<int:contract_id>/payment-rules/<int:rule_id>/status',
        ('POST',),
    ),
    (
        'payments.payment_rule_trigger',
        '/contracts/<int:contract_id>/payment-rules/<int:rule_id>/trigger',
        ('POST',),
    ),
    (
        'production.contract_items_page',
        '/contracts/<int:contract_id>/items',
        ('GET', 'POST'),
    ),
    (
        'production.contract_items_sync_procurement',
        '/contracts/<int:contract_id>/items/sync-procurement',
        ('POST',),
    ),
    (
        'production.production_notice_acknowledge',
        '/production-notices/<int:notice_id>/acknowledge',
        ('POST',),
    ),
    (
        'production.production_notice_cancel',
        '/production-notices/<int:notice_id>/cancel',
        ('POST',),
    ),
    (
        'production.production_notice_close',
        '/production-notices/<int:notice_id>/close',
        ('POST',),
    ),
    (
        'production.production_notice_detail',
        '/production-notices/<int:notice_id>',
        ('GET',),
    ),
    (
        'production.production_notice_edit',
        '/production-notices/<int:notice_id>/edit',
        ('GET', 'POST'),
    ),
    (
        'production.production_notice_issue',
        '/production-notices/<int:notice_id>/issue',
        ('POST',),
    ),
    (
        'production.production_notice_list',
        '/production-notices',
        ('GET',),
    ),
    (
        'production.production_notice_new',
        '/contracts/<int:contract_id>/production-notices/new',
        ('GET', 'POST'),
    ),
    (
        'production.production_notice_revise',
        '/production-notices/<int:notice_id>/revise',
        ('POST',),
    ),
}

CONTRACT_IMPORT_ROUTES = {
    (
        'contract_import.contract_import',
        '/contracts/import',
        ('GET',),
    ),
    (
        'contract_import.contract_import_cancel',
        '/contracts/import/<sid>/cancel',
        ('POST',),
    ),
    (
        'contract_import.contract_import_confirm',
        '/contracts/import/<sid>/confirm',
        ('POST',),
    ),
    (
        'contract_import.contract_import_preview',
        '/contracts/import/preview',
        ('POST',),
    ),
    (
        'contract_import.contract_import_review',
        '/contracts/import/<sid>/review',
        ('GET',),
    ),
}

TEMPLATE_ROUTES = {
    (
        'templates.create_template',
        '/create-template',
        ('GET',),
    ),
    (
        'templates.list_templates',
        '/templates',
        ('GET',),
    ),
    (
        'templates.save_template_defaults',
        '/template-defaults',
        ('POST',),
    ),
    (
        'templates.template_copy',
        '/template/<filename>/copy',
        ('POST',),
    ),
    (
        'templates.template_delete',
        '/template/<filename>/delete',
        ('POST',),
    ),
    (
        'templates.template_editor',
        '/template/<name>',
        ('GET',),
    ),
    (
        'templates.template_manual_save',
        '/template/manual-save',
        ('POST',),
    ),
    (
        'templates.template_preview',
        '/template/<name>/preview',
        ('POST',),
    ),
    (
        'templates.template_version_restore',
        '/template/<name>/versions/'
        '<version_filename>/restore',
        ('POST',),
    ),
    (
        'templates.template_versions',
        '/template/<name>/versions',
        ('GET',),
    ),
    (
        'templates.upload_style',
        '/template/upload-style',
        ('POST',),
    ),
}

PROCUREMENT_ROUTES = {
    (
        'procurement.procurement_award',
        '/procurement/projects/<int:project_id>/award',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_award_document',
        '/procurement/projects/<int:project_id>/award/document',
        ('POST',),
    ),
    (
        'procurement.procurement_clarification_document',
        '/procurement/projects/<int:project_id>/'
        'clarifications/document',
        ('POST',),
    ),
    (
        'procurement.procurement_clarification_update',
        '/procurement/clarifications/<int:question_id>',
        ('POST',),
    ),
    (
        'procurement.procurement_clarifications_generate',
        '/procurement/projects/<int:project_id>/'
        'clarifications/generate',
        ('POST',),
    ),
    (
        'procurement.procurement_comparison',
        '/procurement/projects/<int:project_id>/comparison',
        ('GET',),
    ),
    (
        'procurement.procurement_comparison_export',
        '/procurement/projects/<int:project_id>/comparison/export',
        ('POST',),
    ),
    (
        'procurement.procurement_comparison_run',
        '/procurement/projects/<int:project_id>/comparison/run',
        ('POST',),
    ),
    (
        'procurement.procurement_direct_contract',
        '/procurement/projects/<int:project_id>/direct-contract',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_erp_oa_summary',
        '/procurement/projects/<int:project_id>/erp-oa-summary',
        ('POST',),
    ),
    (
        'procurement.procurement_file_download',
        '/procurement/files/<int:file_id>/download',
        ('GET',),
    ),
    (
        'procurement.procurement_final_commitments',
        '/procurement/projects/<int:project_id>/'
        'negotiation/commitments',
        ('POST',),
    ),
    (
        'procurement.procurement_history_prices',
        '/procurement/history-prices',
        ('GET',),
    ),
    (
        'procurement.procurement_home',
        '/procurement',
        ('GET',),
    ),
    (
        'procurement.procurement_inquiry_document',
        '/procurement/projects/<int:project_id>/inquiry',
        ('POST',),
    ),
    (
        'procurement.procurement_item_add',
        '/procurement/projects/<int:project_id>/items',
        ('POST',),
    ),
    (
        'procurement.procurement_item_delete',
        '/procurement/projects/<int:project_id>/items/'
        '<int:item_id>/delete',
        ('POST',),
    ),
    (
        'procurement.procurement_item_edit',
        '/procurement/projects/<int:project_id>/items/'
        '<int:item_id>/edit',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_items_bulk',
        '/procurement/projects/<int:project_id>/items/bulk',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_items_export',
        '/procurement/projects/<int:project_id>/items/export',
        ('POST',),
    ),
    (
        'procurement.procurement_negotiation',
        '/procurement/projects/<int:project_id>/negotiation',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_negotiation_minutes',
        '/procurement/projects/<int:project_id>/negotiation/minutes',
        ('POST',),
    ),
    (
        'procurement.procurement_negotiation_plan',
        '/procurement/projects/<int:project_id>/negotiation/plan',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_project_archive',
        '/procurement/projects/<int:project_id>/archive',
        ('POST',),
    ),
    (
        'procurement.procurement_project_detail',
        '/procurement/projects/<int:project_id>',
        ('GET',),
    ),
    (
        'procurement.procurement_project_edit',
        '/procurement/projects/<int:project_id>/edit',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_project_new',
        '/procurement/projects/new',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_project_status',
        '/procurement/projects/<int:project_id>/status',
        ('POST',),
    ),
    (
        'procurement.procurement_projects',
        '/procurement/projects',
        ('GET',),
    ),
    (
        'procurement.procurement_quote_confirm',
        '/procurement/quote-imports/<int:job_id>/confirm',
        ('POST',),
    ),
    (
        'procurement.procurement_quote_delete',
        '/procurement/projects/<int:project_id>/quotes/'
        '<int:quote_id>/delete',
        ('POST',),
    ),
    (
        'procurement.procurement_quote_edit',
        '/procurement/projects/<int:project_id>/quotes/'
        '<int:quote_id>/edit',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_quote_import',
        '/procurement/projects/<int:project_id>/quotes/import',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_quote_mapping',
        '/procurement/quote-mappings/<int:job_id>',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_quote_mapping_upload',
        '/procurement/projects/<int:project_id>/quotes/map',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_quote_pdf_upload',
        '/procurement/projects/<int:project_id>/quotes/pdf',
        ('POST',),
    ),
    (
        'procurement.procurement_quote_preview',
        '/procurement/quote-imports/<int:job_id>',
        ('GET',),
    ),
    (
        'procurement.procurement_quote_template',
        '/procurement/projects/<int:project_id>/quote-template/'
        '<int:supplier_id>',
        ('POST',),
    ),
    (
        'procurement.procurement_quote_template_selected',
        '/procurement/projects/<int:project_id>/quote-template',
        ('POST',),
    ),
    (
        'procurement.procurement_supplier_add',
        '/procurement/projects/<int:project_id>/suppliers',
        ('POST',),
    ),
    (
        'procurement.procurement_supplier_delete',
        '/procurement/projects/<int:project_id>/suppliers/'
        '<int:supplier_id>/delete',
        ('POST',),
    ),
    (
        'procurement.procurement_supplier_edit',
        '/procurement/projects/<int:project_id>/suppliers/'
        '<int:supplier_id>/edit',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_to_contract',
        '/procurement/projects/<int:project_id>/to-contract',
        ('GET', 'POST'),
    ),
    (
        'procurement.procurement_workflow_jump',
        '/procurement/projects/<int:project_id>/workflow/jump',
        ('POST',),
    ),
}

CONTRACT_ROUTES = {
    (
        'contracts.contract_batch_delete',
        '/contracts/batch-delete',
        ('POST',),
    ),
    (
        'contracts.contract_batch_status',
        '/contracts/batch-status',
        ('POST',),
    ),
    (
        'contracts.contract_detail',
        '/contracts/<int:contract_id>',
        ('GET',),
    ),
    (
        'contracts.contract_download',
        '/contracts/<int:contract_id>/download',
        ('GET',),
    ),
    (
        'contracts.contract_export',
        '/contracts/export',
        ('POST',),
    ),
    (
        'contracts.contract_ledger',
        '/contracts',
        ('GET',),
    ),
    (
        'contracts.contract_permanent_delete',
        '/contracts/<int:contract_id>/permanent-delete',
        ('POST',),
    ),
    (
        'contracts.contract_restore',
        '/contracts/<int:contract_id>/restore',
        ('POST',),
    ),
    (
        'contracts.contract_soft_delete',
        '/contracts/<int:contract_id>/soft-delete',
        ('POST',),
    ),
    (
        'contracts.contract_trash',
        '/contracts/trash',
        ('GET',),
    ),
    (
        'contracts.contract_update',
        '/contracts/<int:contract_id>/update',
        ('POST',),
    ),
    ('contracts.editor', '/editor', ('GET',)),
    ('contracts.generate', '/generate', ('POST',)),
    (
        'contracts.generate_batch',
        '/generate-batch',
        ('POST',),
    ),
    (
        'contracts.generate_preflight',
        '/generate/preflight',
        ('POST',),
    ),
    ('contracts.index', '/', ('GET',)),
}


def test_payment_and_production_route_contracts_are_stable(app):
    actual = {
        (
            rule.endpoint,
            rule.rule,
            tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'})),
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith(('payments.', 'production.'))
    }
    assert actual == PAYMENT_AND_PRODUCTION_ROUTES


def test_contract_import_route_contracts_are_stable(app):
    actual = {
        (
            rule.endpoint,
            rule.rule,
            tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'})),
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith('contract_import.')
    }
    assert actual == CONTRACT_IMPORT_ROUTES


def test_template_route_contracts_are_stable(app):
    actual = {
        (
            rule.endpoint,
            rule.rule,
            tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'})),
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith('templates.')
    }
    assert actual == TEMPLATE_ROUTES


def test_procurement_route_contracts_are_stable(app):
    actual = {
        (
            rule.endpoint,
            rule.rule,
            tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'})),
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith('procurement.')
    }
    assert actual == PROCUREMENT_ROUTES


def test_contract_route_contracts_are_stable(app):
    actual = {
        (
            rule.endpoint,
            rule.rule,
            tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'})),
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith('contracts.')
    }
    assert actual == CONTRACT_ROUTES
