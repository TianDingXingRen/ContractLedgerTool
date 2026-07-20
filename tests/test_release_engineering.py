import re
from pathlib import Path

import _pyinstaller_common


ROOT = Path(__file__).resolve().parents[1]


def test_project_version_is_semantic_and_used_by_packaging(tmp_path):
    version = (ROOT / 'version.txt').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?', version)
    assert _pyinstaller_common.project_version() == version
    assert _pyinstaller_common.write_version_file(tmp_path) == version
    assert (tmp_path / 'version.txt').read_text(encoding='utf-8') == version

    version_info = _pyinstaller_common.write_windows_version_info(
        tmp_path, 'ContractLedgerTool'
    )
    content = version_info.read_text(encoding='utf-8')
    assert "StringStruct(u'ProductVersion', u'" + version + "')" in content
    assert "StringStruct(u'OriginalFilename', u'ContractLedgerTool.exe')" in content


def test_build_metadata_records_git_revision_and_dirty_state():
    metadata = _pyinstaller_common.source_metadata()
    assert re.fullmatch(r'[0-9a-f]{40}|unknown', metadata['source_commit'])
    assert isinstance(metadata['source_dirty'], bool)


def test_development_toolchain_is_fully_pinned():
    lock = (ROOT / 'requirements-dev.lock').read_text(encoding='utf-8')
    pinned = [
        line.strip()
        for line in lock.splitlines()
        if line.strip() and not line.lstrip().startswith(('#', '-r'))
    ]
    assert '-r requirements.lock' in lock
    assert {'pytest', 'ruff', 'pytest-cov', 'playwright', 'pyinstaller'} <= {
        line.split('==', 1)[0].lower() for line in pinned
    }
    assert all(line.count('==') == 1 for line in pinned)


def test_ci_and_release_workflows_use_the_shared_quality_gate():
    ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    release = (
        ROOT / '.github' / 'workflows' / 'release.yml'
    ).read_text(encoding='utf-8')

    assert 'python scripts/quality_gate.py ci' in ci
    assert 'requirements-dev.lock' in ci
    assert 'playwright install chromium' in ci
    assert 'build/coverage.xml' in ci

    assert 'python scripts/quality_gate.py release --build-installer' in release
    assert 'RELEASE_TAG:' in release
    assert 'ContractLedgerTool_OfflineInstaller.exe' in release
    assert 'python scripts/generate_sbom.py' in release
    assert 'ContractLedgerTool.sbom.cdx.json' in release
    assert 'SHA256SUMS' in release
    assert 'actions/attest@v4' in release
    assert 'gh release create' in release
    assert 'CODESIGN_PFX_BASE64' in release
    assert 'CODESIGN_PFX_PASSWORD' in release
    assert 'REQUIRE_CODE_SIGNING=1' in release

    quality_gate = (ROOT / 'scripts' / 'quality_gate.py').read_text(encoding='utf-8')
    assert 'MODULE_COVERAGE_FLOORS' in quality_gate
    assert 'check_release_tree_clean()' in quality_gate
    assert 'check_authenticode(RELEASE_EXE)' in quality_gate


def test_installer_registers_standard_uninstaller_and_opt_in_autostart():
    install_script = (ROOT / 'installer_assets' / 'install.ps1').read_text(
        encoding='utf-8'
    )
    uninstall_script = (ROOT / 'installer_assets' / 'uninstall.ps1').read_text(
        encoding='utf-8'
    )

    assert 'CurrentVersion\\Uninstall\\ContractLedgerTool' in install_script
    assert 'QuietUninstallString' in install_script
    assert '[switch]$EnableAutostart' in install_script
    assert 'if ($EnableAutostart -and -not $NoAutostart)' in install_script
    assert '[switch]$RemoveData' in uninstall_script
    assert 'Contracts, ledger, templates, settings, and backups were kept' in uninstall_script


def test_open_source_governance_files_are_present():
    expected = [
        'LICENSE',
        'NOTICE',
        'CONTRIBUTING.md',
        'SECURITY.md',
        '.github/CODEOWNERS',
        '.github/dependabot.yml',
        '.github/pull_request_template.md',
        '.github/ISSUE_TEMPLATE/bug_report.yml',
        '.github/ISSUE_TEMPLATE/feature_request.yml',
        '.github/workflows/codeql.yml',
    ]
    for relative_path in expected:
        assert (ROOT / relative_path).is_file(), relative_path

    notice = (ROOT / 'NOTICE').read_text(encoding='utf-8')
    assert 'Copyright (c) 2026 Shao' in notice
    assert 'MIT License' in notice


def test_release_configuration_uses_single_version_source():
    config = (ROOT / '.releaserc.yml').read_text(encoding='utf-8')
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    quality_gate = (ROOT / 'scripts' / 'quality_gate.py').read_text(
        encoding='utf-8'
    )

    assert 'file: version.txt' in config
    assert 'path: CHANGELOG.md' in config
    assert 'expected_tag != f\'v{version}\'' in quality_gate
    assert f'## {_pyinstaller_common.project_version()} - ' in changelog


def test_changelog_latest_release_matches_version_file():
    version = (ROOT / 'version.txt').read_text(encoding='utf-8').strip()
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    releases = re.findall(
        r'^##\s+(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s+-\s+(\d{4}-\d{2}-\d{2})$',
        changelog,
        flags=re.MULTILINE,
    )
    assert releases
    assert releases[0] == (version, '2026-07-20')
    assert len({release_version for release_version, _date in releases}) == len(releases)
