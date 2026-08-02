"""Shared procurement persistence constants."""

PROJECT_STATUSES = frozenset({
    'draft',
    'documents_ready',
    'inquiry_sent',
    'quotes_received',
    'clarifying',
    'negotiating',
    'award_draft',
    'award_confirmed',
    'contract_draft',
    'contract_created',
    'archived',
})

AWARD_CONFIRMED_STATUS = 'award_confirmed'
CONTRACT_CREATED_STATUS = 'contract_created'
DEFAULT_CONTRACT_ROLLBACK_STATUS = AWARD_CONFIRMED_STATUS
