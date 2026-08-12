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

STATUS_TRANSITIONS = {
    'draft': {'documents_ready', 'inquiry_sent', 'quotes_received', 'archived'},
    'documents_ready': {'draft', 'inquiry_sent', 'quotes_received', 'archived'},
    'inquiry_sent': {'documents_ready', 'quotes_received', 'archived'},
    'quotes_received': {
        'inquiry_sent', 'clarifying', 'negotiating', 'award_draft',
        'award_confirmed', 'archived',
    },
    'clarifying': {
        'quotes_received', 'negotiating', 'award_draft', 'award_confirmed',
        'archived',
    },
    'negotiating': {
        'quotes_received', 'clarifying', 'award_draft', 'award_confirmed',
        'archived',
    },
    'award_draft': {'quotes_received', 'award_confirmed', 'archived'},
    'award_confirmed': {'award_draft', 'contract_draft', 'archived'},
    'contract_draft': {'award_confirmed', 'contract_created', 'archived'},
    'contract_created': {'archived'},
    'archived': {'draft', 'contract_created'},
}

WORKFLOW_STATUS_ORDER = (
    'draft', 'documents_ready', 'inquiry_sent', 'quotes_received', 'clarifying',
    'negotiating', 'award_draft', 'award_confirmed', 'contract_draft',
    'contract_created', 'archived',
)

AWARD_CONFIRMED_STATUS = 'award_confirmed'
CONTRACT_CREATED_STATUS = 'contract_created'
DEFAULT_CONTRACT_ROLLBACK_STATUS = AWARD_CONFIRMED_STATUS
