"""Regression tests for the repository architecture inventory and ratchets."""

import ast

import pytest

from scripts import architecture_check


pytestmark = pytest.mark.fast


def _relative_production_files():
    return {
        path.relative_to(architecture_check.ROOT).as_posix()
        for path in architecture_check.python_files()
    }


def test_architecture_inventory_covers_packages_and_top_level_modules():
    files = _relative_production_files()

    assert {
        'payment_extraction/parser.py',
        'xlsx_export/columns.py',
        'app.py',
        'config.py',
        'docx_builder.py',
        'excel_bill_service.py',
        'field_eval.py',
        'payment_extractor.py',
        'template_def.py',
        'xlsx_exporter.py',
    } <= files
    assert len(files) == len(list(architecture_check.python_files()))


def test_legacy_file_budgets_match_current_size():
    for relative, budget in architecture_check.LEGACY_FILE_BUDGETS.items():
        source = (architecture_check.ROOT / relative).read_text(encoding='utf-8')
        assert architecture_check.logical_line_count(source) == budget


def test_legacy_function_budgets_match_current_size():
    trees = {}
    for (relative, function_name), budget in (
        architecture_check.LEGACY_FUNCTION_BUDGETS.items()
    ):
        tree = trees.setdefault(
            relative,
            ast.parse(
                (architecture_check.ROOT / relative).read_text(encoding='utf-8'),
                filename=relative,
            ),
        )
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ]
        assert len(matches) == 1
        function = matches[0]
        assert function.end_lineno - function.lineno + 1 == budget
