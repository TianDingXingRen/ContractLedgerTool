"""Run repeatable commit, CI, and release verification profiles."""

from __future__ import annotations

import argparse
import json
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
MODULE_COVERAGE_FLOORS = {
    'routes/contract_import_confirmation_routes.py': 85,
    'routes/contract_import_upload_routes.py': 80,
    'routes/contract_batch_generation_routes.py': 75,
    'routes/contract_editor_routes.py': 80,
    'routes/contract_generation_routes.py': 80,
    'routes/contract_ledger_routes.py': 85,
    'routes/contracts_bp.py': 90,
    'routes/contract_item_routes.py': 55,
    'routes/excel_bill_bp.py': 45,
    'routes/payment_contract_routes.py': 60,
    'routes/payment_export_routes.py': 80,
    'routes/payment_plan_routes.py': 65,
    'routes/procurement_bp.py': 90,
    'routes/procurement_contract_routes.py': 80,
    'routes/procurement_decision_routes.py': 80,
    'routes/procurement_document_routes.py': 80,
    'routes/procurement_import_routes.py': 80,
    'routes/procurement_item_supplier_routes.py': 85,
    'routes/procurement_project_routes.py': 90,
    'routes/procurement_quote_routes.py': 80,
    'routes/procurement_route_support.py': 75,
    'routes/production_notice_action_routes.py': 70,
    'routes/production_notice_routes.py': 60,
    'routes/template_authoring_routes.py': 85,
    'routes/template_catalog_routes.py': 85,
    'routes/template_default_routes.py': 90,
    'routes/template_version_routes.py': 85,
    'routes/templates_bp.py': 90,
    'services/contract_import_service.py': 50,
    'services/contract_import_workflow.py': 75,
    'services/contract_batch_generation_service.py': 80,
    'services/contract_editor_service.py': 75,
    'services/contract_ledger_service.py': 80,
    'services/handover_service.py': 75,
    'services/payment_commands.py': 80,
    'services/payment_queries.py': 75,
    'services/production_commands.py': 70,
    'services/production_queries.py': 80,
    'services/procurement_contract_handoff_service.py': 80,
    'services/procurement_project_service.py': 70,
    'services/quote_mapping_service.py': 72,
    'services/template_authoring_service.py': 70,
    'services/template_catalog_service.py': 90,
    'services/template_defaults_service.py': 70,
    'services/template_version_service.py': 75,
    'field_eval.py': 75,
    'utils/contract_import_forms.py': 75,
    'utils/payment_forms.py': 80,
    'utils/production_forms.py': 85,
    'utils/template_forms.py': 70,
}


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
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    releases = re.findall(
        r'^##\s+((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)'
        r'(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)\s+-\s+(\d{4}-\d{2}-\d{2})\s*$',
        changelog,
        flags=re.MULTILINE,
    )
    if not releases:
        raise RuntimeError('CHANGELOG.md 缺少语义版本发布记录')
    if releases[0][0] != version:
        raise RuntimeError(
            f'CHANGELOG.md 最新版本 {releases[0][0]!r} 与 version.txt 中的 {version!r} 不一致'
        )
    versions = [release_version for release_version, _date in releases]
    if len(versions) != len(set(versions)):
        raise RuntimeError('CHANGELOG.md 包含重复版本记录')
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
    compiled_css = ROOT / 'static' / 'css' / 'app.min.css'
    before = compiled_css.read_bytes() if compiled_css.is_file() else None
    run([npm, 'run', 'build:css'])
    after = compiled_css.read_bytes() if compiled_css.is_file() else None
    if before is None or after != before:
        raise RuntimeError(
            '生产 CSS 不是可重复构建结果，请提交 npm run build:css 生成的最新产物'
        )


def run_full_tests_with_coverage():
    build_dir = ROOT / 'build'
    build_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix='quality-gate-',
        dir=build_dir,
    ) as temporary_root:
        temporary_root = Path(temporary_root)
        cache_dir = temporary_root / 'cache'
        run(
            [
                sys.executable,
                '-m',
                'pytest',
                '-q',
                '-m',
                'not performance',
                f'--basetemp={temporary_root / "nonperformance"}',
                '-o',
                f'cache_dir={cache_dir}',
                '--cov=.',
                '--cov-report=term',
                '--cov-report=xml:build/coverage.xml',
                '--cov-report=json:build/coverage.json',
            ]
        )
        check_module_coverage(build_dir / 'coverage.json')
        run(
            [
                sys.executable,
                '-m',
                'pytest',
                '-m',
                'performance',
                '-q',
                f'--basetemp={temporary_root / "performance"}',
                '-o',
                f'cache_dir={cache_dir}',
            ]
        )


def check_module_coverage(report_path):
    report = json.loads(Path(report_path).read_text(encoding='utf-8'))
    files = {
        str(name).replace('\\', '/'): details
        for name, details in report.get('files', {}).items()
    }
    failures = []
    for module, floor in MODULE_COVERAGE_FLOORS.items():
        details = files.get(module)
        if details is None:
            failures.append(f'{module}: coverage report missing')
            continue
        covered = float(details['summary']['percent_covered'])
        if covered + 1e-9 < floor:
            failures.append(f'{module}: {covered:.2f}% < {floor}%')
    if failures:
        raise RuntimeError('关键模块覆盖率未达标：\n' + '\n'.join(failures))
    print('Critical module coverage floors passed')


def check_release_tree_clean():
    result = subprocess.run(
        ['git', 'status', '--porcelain', '--untracked-files=normal'],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    if result.stdout.strip():
        raise RuntimeError('发布构建必须来自无未提交改动的 Git 工作区')


def require_signing_configuration():
    pfx_path = os.environ.get('CODESIGN_PFX', '').strip()
    thumbprint = os.environ.get('CODESIGN_CERT_THUMBPRINT', '').strip()
    if bool(pfx_path) == bool(thumbprint):
        raise RuntimeError(
            '正式发布必须且只能配置一种代码签名身份：'
            'CODESIGN_PFX 或 CODESIGN_CERT_THUMBPRINT'
        )
    if pfx_path:
        if not Path(pfx_path).is_file():
            raise FileNotFoundError(f'代码签名 PFX 不存在：{pfx_path}')
        if not os.environ.get('CODESIGN_PFX_PASSWORD'):
            raise RuntimeError('使用 PFX 发布时必须配置 CODESIGN_PFX_PASSWORD')
    os.environ['REQUIRE_CODE_SIGNING'] = '1'


def check_authenticode(executable):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f'未找到待签名验证 EXE：{executable}')
    script = (
        "$signature = Get-AuthenticodeSignature -LiteralPath $args[0]; "
        "if ($signature.Status -ne 'Valid') { "
        "throw ('Authenticode signature is not valid: ' + $signature.Status) }; "
        "if (-not $signature.TimeStamperCertificate) { "
        "throw 'Authenticode signature has no trusted timestamp' }; "
        "Write-Host ('Authenticode signature valid: ' + $args[0])"
    )
    run(['powershell', '-NoProfile', '-Command', script, str(executable)])


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
    if args.profile == 'release':
        check_release_tree_clean()
    run([sys.executable, 'scripts/architecture_check.py'])
    run([sys.executable, '-m', 'ruff', 'check', '.'])

    if args.profile == 'commit':
        run([sys.executable, '-m', 'pytest', '-m', 'fast', '-q'])
        return

    run_full_tests_with_coverage()
    run([sys.executable, 'scripts/office_compatibility_check.py'])
    check_javascript()
    check_css()

    if args.profile == 'release' and args.build_installer:
        require_signing_configuration()
        run([sys.executable, 'build_package.py', 'installer'])
    if args.profile == 'release':
        if not args.skip_exe:
            check_executable(args.exe)
            check_authenticode(args.exe)
        check_release_outputs()
        check_authenticode(RELEASE_EXE)


if __name__ == '__main__':
    main()
