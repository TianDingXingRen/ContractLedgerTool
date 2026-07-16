"""Run the repeatable commit or release verification profile."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'dist' / 'desktop_exe' / 'ContractLedgerTool.exe'


def run(command):
    print(f"\n> {' '.join(map(str, command))}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def check_javascript():
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js 不可用，无法执行 JavaScript 语法检查')
    for script in sorted((ROOT / 'static' / 'js').glob('*.js')):
        run([node, '--check', str(script)])


def check_executable(executable):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f'未找到待自检 EXE：{executable}')
    with tempfile.TemporaryDirectory(prefix='contract-tool-exe-check-') as runtime_dir:
        run([str(executable), '--self-check', '--runtime-dir', runtime_dir])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('profile', choices=('commit', 'release'))
    parser.add_argument('--exe', default=str(DEFAULT_EXE))
    parser.add_argument('--skip-exe', action='store_true')
    args = parser.parse_args()

    run([sys.executable, '-m', 'ruff', 'check', '.'])
    if args.profile == 'commit':
        run([sys.executable, '-m', 'pytest', '-m', 'fast', '-q'])
        return

    run([sys.executable, '-m', 'pytest', '-q'])
    check_javascript()
    run(['npm', 'run', 'build:css'])
    if not args.skip_exe:
        check_executable(args.exe)


if __name__ == '__main__':
    main()
