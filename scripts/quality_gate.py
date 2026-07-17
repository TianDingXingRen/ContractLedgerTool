"""Run repeatable commit, CI, and release verification profiles."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = (
    ROOT / 'build' / 'offline_installer_package' / 'ContractLedgerTool.exe'
)
RELEASE_EXE = (
    ROOT / 'dist' / 'release' / 'ContractLedgerTool_OfflineInstaller.exe'
)
SEMVER_PATTERN = re.compile(
    r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
    r'(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$'
)


def run(command):
    print(f"\n> {' '.join(map(str, command))}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def check_version():
    version = (ROOT / 'version.txt').read_text(encoding='utf-8').strip()
    if not SEMVER_PATTERN.fullmatch(version):
        raise RuntimeError(f'version.txt 不是有效的语义版本：{version!r}')
    expected_tag = os.environ.get('RELEASE_TAG', '').strip()
    if expected_tag and expected_tag != f'v{version}':
        raise RuntimeError(
            f'发布标签 {expected_tag!r} 与 version.txt 中的 v{version} 不一致'
        )
    print(f'Version check passed: {version}')


def check_javascript():
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js 不可用，无法执行 JavaScript 语法检查')
    for script in sorted((ROOT / 'static' / 'js').glob('*.js')):
        run([node, '--check', str(script)])


def check_css():
    npm = shutil.which('npm')
    if not npm:
        raise RuntimeError('npm 不可用，无法验证生产 CSS 构建')
    run([npm, 'run', 'build:css'])
    run(['git', 'diff', '--exit-code', '--', 'static/css/app.min.css'])


def run_full_tests_with_coverage():
    (ROOT / 'build').mkdir(exist_ok=True)
    run(
        [
            sys.executable,
            '-m',
            'pytest',
            '-q',
            '--cov=.',
            '--cov-report=term',
            '--cov-report=xml:build/coverage.xml',
            '--cov-report=json:build/coverage.json',
        ]
    )


def check_executable(executable):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f'未找到待自检 EXE：{executable}')
    with tempfile.TemporaryDirectory(prefix='contract-tool-exe-check-') as runtime_dir:
        run([str(executable), '--self-check', '--runtime-dir', runtime_dir])


def check_release_outputs():
    if not RELEASE_EXE.is_file():
        raise FileNotFoundError(f'发布安装包不存在：{RELEASE_EXE}')
    extra_installers = [
        path
        for path in (ROOT / 'dist').rglob('*.exe')
        if path.resolve() != RELEASE_EXE.resolve()
    ]
    if extra_installers:
        raise RuntimeError(f'dist 中存在多余安装包：{extra_installers}')
    print(f'Release artifact check passed: {RELEASE_EXE}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('profile', choices=('commit', 'ci', 'release'))
    parser.add_argument('--exe', default=str(DEFAULT_EXE))
    parser.add_argument('--skip-exe', action='store_true')
    parser.add_argument('--build-installer', action='store_true')
    args = parser.parse_args()

    check_version()
    run([sys.executable, 'scripts/architecture_check.py'])
    run([sys.executable, '-m', 'ruff', 'check', '.'])

    if args.profile == 'commit':
        run([sys.executable, '-m', 'pytest', '-m', 'fast', '-q'])
        return

    run_full_tests_with_coverage()
    check_javascript()
    check_css()

    if args.profile == 'release' and args.build_installer:
        run([sys.executable, 'build_installer.py'])
    if args.profile == 'release':
        if not args.skip_exe:
            check_executable(args.exe)
        check_release_outputs()


if __name__ == '__main__':
    main()
