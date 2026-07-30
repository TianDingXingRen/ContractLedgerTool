"""Deterministic payment extraction pipeline.

The package keeps the three processing stages explicit:

* :mod:`tokenizer` finds payment clauses and extracts lexical values.
* :mod:`parser` turns one clause into a semantic payment node.
* :mod:`resolver` resolves nodes into persisted rules and actionable plans.
"""

from payment_extraction.resolver import PaymentExtractionResult

__all__ = ['PaymentExtractionResult']
