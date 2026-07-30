"""Enforce lightweight maintainability boundaries without changing public APIs."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (
    'core',
    'database',
    'ledger_store',
    'procurement_store',
    'routes',
    'runtime',
    'services',
    'utils',
)
MAX_LOGICAL_LINES = 650
MAX_FUNCTION_LINES = 150

# Existing large route registrars are tracked as explicit debt. Their budgets
# prevent further growth while allowing incremental extraction without a rewrite.
LEGACY_FILE_BUDGETS = {
    'services/handover_service.py': 690,
}
LEGACY_FUNCTION_BUDGETS = {
    ('routes/excel_bill_bp.py', 'register'): 180,
    ('routes/settings_bp.py', 'register'): 218,
    ('services/handover_service.py', 'build_handover_data'): 207,
}
SLIM_BLUEPRINT_BUDGETS = {
    'routes/contract_import_bp.py': 100,
    'routes/contracts_bp.py': 100,
    'routes/payments_bp.py': 100,
    'routes/procurement_bp.py': 100,
    'routes/production_bp.py': 100,
    'routes/templates_bp.py': 100,
}
ROUTE_LAYER_FORBIDDEN_IMPORTS = {
    'ledger_store',
    'procurement_store',
    'xlsx_exporter',
    'pdf_exporter',
    'sqlite3',
    'openpyxl',
}
# These files are the remaining migration queue. A dependency may only leave
# this list; adding new route-to-infrastructure coupling fails the check.
ROUTE_DEPENDENCY_ALLOWLIST = {
    'routes/contract_download_routes.py': {
        'ledger_store',
        'pdf_exporter',
    },
    'routes/contract_workspace.py': {
        'ledger_store',
        'procurement_store',
    },
    'routes/invoices_bp.py': {'ledger_store'},
    'routes/settings_bp.py': {'ledger_store', 'pdf_exporter'},
}
INNER_LAYER_ROOTS = {
    'core',
    'database',
    'ledger_store',
    'procurement_store',
    'runtime',
    'services',
    'utils',
}
FORBIDDEN_INNER_IMPORTS = {'app', 'routes'}
ROUTE_BLUEPRINT_MODULES = (
    'contract_import_bp.py',
    'contracts_bp.py',
    'excel_bill_bp.py',
    'invoices_bp.py',
    'payments_bp.py',
    'procurement_bp.py',
    'production_bp.py',
    'settings_bp.py',
    'templates_bp.py',
)
URL_FOR_PATTERN = re.compile(r"""url_for\(\s*['"]([^'"]+)['"]""")


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
    file_budget = SLIM_BLUEPRINT_BUDGETS.get(
        relative,
        LEGACY_FILE_BUDGETS.get(relative, MAX_LOGICAL_LINES),
    )
    if logical_lines > file_budget:
        errors.append(
            f'{relative}: {logical_lines} logical lines exceeds {file_budget}'
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


def check_route_layer_dependencies(path):
    """Keep HTTP adapters from reaching stores and artifact generators."""
    relative = path.relative_to(ROOT).as_posix()
    if not relative.startswith('routes/'):
        return []

    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=relative)
    imported = set()
    first_lines = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for root in imported_roots(node):
            if root in ROUTE_LAYER_FORBIDDEN_IMPORTS:
                imported.add(root)
                first_lines.setdefault(root, node.lineno)

    allowed = ROUTE_DEPENDENCY_ALLOWLIST.get(relative, set())
    errors = []
    for root in sorted(imported - allowed):
        errors.append(
            f'{relative}:{first_lines[root]} route layer imports '
            f'forbidden infrastructure dependency {root!r}'
        )
    stale = allowed - imported
    if stale:
        errors.append(
            f'{relative}: remove stale route dependency allowlist entries: '
            f'{", ".join(sorted(stale))}'
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


def check_endpoint_namespacing():
    errors = []
    legacy_blueprint = ROOT / 'routes' / 'legacy_blueprint.py'
    if legacy_blueprint.exists():
        errors.append('routes/legacy_blueprint.py: legacy endpoint bridge must stay removed')

    for filename in ROUTE_BLUEPRINT_MODULES:
        path = ROOT / 'routes' / filename
        source = path.read_text(encoding='utf-8')
        if 'Blueprint(' not in source:
            errors.append(f'routes/{filename}: must use Flask Blueprint directly')
        if 'LegacyEndpointBlueprint' in source:
            errors.append(f'routes/{filename}: imports the removed legacy endpoint bridge')

    for path in python_files():
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=path.relative_to(ROOT).as_posix())
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'url_for'
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            endpoint = node.args[0].value
            if endpoint != 'static' and '.' not in endpoint:
                errors.append(
                    f'{path.relative_to(ROOT).as_posix()}:{node.lineno} '
                    f'url_for endpoint {endpoint!r} is not blueprint-qualified'
                )

    for path in sorted((ROOT / 'templates').rglob('*.html')):
        for line_number, line in enumerate(
            path.read_text(encoding='utf-8').splitlines(),
            1,
        ):
            for endpoint in URL_FOR_PATTERN.findall(line):
                if endpoint != 'static' and '.' not in endpoint:
                    errors.append(
                        f'{path.relative_to(ROOT).as_posix()}:{line_number} '
                        f'url_for endpoint {endpoint!r} is not blueprint-qualified'
                    )
    return errors


def check_build_entry_point():
    errors = []
    for filename in ('build_desktop_exe.py', 'build_installer.py'):
        if (ROOT / filename).exists():
            errors.append(f'{filename}: obsolete delegated build entry point exists')
    build_entry = (ROOT / 'build_package.py').read_text(encoding='utf-8')
    tree = ast.parse(build_entry, filename='build_package.py')
    subcommands = {
        node.args[0].value
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'add_parser'
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )
    }
    for command in ('app', 'installer', 'desktop'):
        if command not in subcommands:
            errors.append(f'build_package.py: missing {command!r} subcommand')
    return errors


def main():
    errors = []
    files = list(python_files())
    for path in files:
        errors.extend(check_file(path))
        errors.extend(check_route_layer_dependencies(path))
    for path in exception_policy_files():
        errors.extend(check_silent_exception_handlers(path))
    errors.extend(check_endpoint_namespacing())
    errors.extend(check_build_entry_point())
    if errors:
        raise SystemExit('Architecture check failed:\n- ' + '\n- '.join(errors))
    print(f'Architecture check passed for {len(files)} production modules.')


if __name__ == '__main__':
    main()
