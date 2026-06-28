"""Group git worktree changes by functional area.

This is a lightweight audit helper for large, dirty worktrees. It does not
stage, revert, or modify files.
"""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict


def _clean_status_path(path):
    if ' -> ' in path:
        path = path.split(' -> ', 1)[1]
    return path.strip().strip('"').replace('\\', '/')


def parse_status_line(line):
    if not line.strip():
        return None
    status = line[:2].strip() or line[:2]
    path = _clean_status_path(line[3:] if len(line) > 3 else '')
    if not path:
        return None
    return status, path


def categorize_path(path):
    normalized = path.replace('\\', '/')
    basename = normalized.rsplit('/', 1)[-1]
    if (
        normalized.startswith(('data/', 'output/', 'uploads/', 'sessions/', 'logs/'))
        or basename.endswith(('.db', '.db-wal', '.db-shm', '.log'))
    ):
        return 'runtime-data'
    if normalized.startswith(('ledger_store/', 'procurement_store/')):
        return 'stores'
    if normalized.startswith(('routes/', 'services/')):
        return 'routes-services'
    if normalized.startswith(('templates/', 'static/')):
        return 'frontend'
    if normalized.startswith('tests/') or basename.startswith('test_'):
        return 'tests'
    if (
        normalized.startswith('installer_assets/')
        or basename.startswith(('build_', '_pyinstaller'))
        or basename in {'requirements.txt', 'version.txt'}
        or basename.endswith(('.bat', '.ps1', '.spec'))
    ):
        return 'packaging'
    if (
        normalized.startswith(('docs/', 'design/', 'scripts/'))
        or basename.lower().endswith('.md')
        or basename in {'README.md', '.gitignore'}
    ):
        return 'docs-tooling'
    if (
        normalized.startswith('utils/')
        or basename in {'app.py', 'config.py'}
        or basename.startswith(('app_', 'runtime_'))
    ):
        return 'backend-core'
    return 'other'


def summarize(lines):
    grouped = defaultdict(list)
    for line in lines:
        parsed = parse_status_line(line)
        if not parsed:
            continue
        status, path = parsed
        grouped[categorize_path(path)].append((status, path))
    return dict(sorted(grouped.items()))


def git_status_lines():
    result = subprocess.run(
        ['git', 'status', '--short'],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.splitlines()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Group git status by project area.')
    parser.add_argument('--limit', type=int, default=20, help='max paths to print per group')
    args = parser.parse_args(argv)

    grouped = summarize(git_status_lines())
    for category, entries in grouped.items():
        print(f'[{category}] {len(entries)}')
        for status, path in entries[:args.limit]:
            print(f'  {status:2} {path}')
        if len(entries) > args.limit:
            print(f'  ... {len(entries) - args.limit} more')


if __name__ == '__main__':
    main()
