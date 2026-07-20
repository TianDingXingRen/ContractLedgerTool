"""Enforce lightweight maintainability boundaries without changing public APIs."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (
    'core',
    'ledger_store',
    'procurement_store',
    'routes',
    'runtime',
    'services',
    'utils',
)
MAX_LOGICAL_LINES = 700
MAX_FUNCTION_LINES = 150

# Existing large route registrars are tracked as explicit debt. Their budgets
# prevent further growth while allowing incremental extraction without a rewrite.
LEGACY_FUNCTION_BUDGETS = {
    ('routes/contracts_bp.py', 'register'): 625,
    ('routes/contracts_bp.py', 'generate_batch'): 170,
    ('routes/excel_bill_bp.py', 'register'): 180,
    ('routes/payments_bp.py', 'register'): 240,
    ('routes/procurement_bp.py', 'register'): 630,
    ('routes/settings_bp.py', 'register'): 210,
    ('routes/templates_bp.py', 'register'): 525,
    ('services/handover_service.py', 'build_handover_data'): 205,
}
INNER_LAYER_ROOTS = {
    'core',
    'ledger_store',
    'procurement_store',
    'runtime',
    'services',
    'utils',
}
FORBIDDEN_INNER_IMPORTS = {'app', 'routes'}


def python_files():
    for root_name in PRODUCTION_ROOTS:
        yield from sorted((ROOT / root_name).rglob('*.py'))


def exception_policy_files():
    """Yield first-party runtime/build files covered by the no-silent-failure rule."""
    candidates = list(python_files())
    candidates.extend(ROOT.glob('*.py'))
    candidates.extend((ROOT / 'scripts').rglob('*.py'))
    seen = set()
    for path in sorted(candidates):
        if path.name == 'conftest.py' or path in seen:
            continue
        seen.add(path)
        yield path


def logical_line_count(source):
    return sum(
        1
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    )


def imported_roots(node):
    if isinstance(node, ast.Import):
        return {alias.name.split('.')[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module.split('.')[0]}
    return set()


def check_file(path):
    relative = path.relative_to(ROOT).as_posix()
    source = path.read_text(encoding='utf-8')
    errors = []
    logical_lines = logical_line_count(source)
    if logical_lines > MAX_LOGICAL_LINES:
        errors.append(
            f'{relative}: {logical_lines} logical lines exceeds {MAX_LOGICAL_LINES}'
        )

    tree = ast.parse(source, filename=relative)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            budget = LEGACY_FUNCTION_BUDGETS.get(
                (relative, node.name), MAX_FUNCTION_LINES
            )
            if length > budget:
                errors.append(
                    f'{relative}:{node.lineno} {node.name}() has {length} lines; '
                    f'budget is {budget}'
                )

    if relative.split('/')[0] in INNER_LAYER_ROOTS:
        for node in ast.walk(tree):
            forbidden = imported_roots(node) & FORBIDDEN_INNER_IMPORTS
            if forbidden:
                errors.append(
                    f'{relative}:{getattr(node, "lineno", 1)} inner layer imports '
                    f'{", ".join(sorted(forbidden))}'
                )
    return errors


def check_silent_exception_handlers(path):
    """Reject exception handlers that discard failures with a lone pass."""
    relative = path.relative_to(ROOT).as_posix()
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=relative)
    errors = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            errors.append(
                f'{relative}:{node.lineno} silently discards an exception; '
                'log, translate, or re-raise it'
            )
    return errors


def main():
    errors = []
    files = list(python_files())
    for path in files:
        errors.extend(check_file(path))
    for path in exception_policy_files():
        errors.extend(check_silent_exception_handlers(path))
    if errors:
        raise SystemExit('Architecture check failed:\n- ' + '\n- '.join(errors))
    print(f'Architecture check passed for {len(files)} production modules.')


if __name__ == '__main__':
    main()
