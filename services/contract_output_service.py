"""Output-format operations for generated contracts."""

from __future__ import annotations

import os

import pdf_exporter


def generated_pdf_path(docx_path: str) -> str:
    """Return the immutable PDF identity paired with one generated DOCX."""
    return os.path.splitext(os.path.abspath(docx_path))[0] + '.pdf'


def convert_generated_pdf(docx_path: str) -> str:
    """Convert a generated DOCX beside its source and return the PDF path."""
    pdf_path = generated_pdf_path(docx_path)
    pdf_exporter.convert_docx_to_pdf(docx_path, pdf_path)
    return pdf_path
