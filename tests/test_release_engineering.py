import importlib.util
import re
from datetime import datetime
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


def test_installer_registers_standard_uninstaller_and_default_autostart():
    install_script = (ROOT / 'installer_assets' / 'install.ps1').read_text(
        encoding='utf-8'
    )
    uninstall_script = (ROOT / 'installer_assets' / 'uninstall.ps1').read_text(
        encoding='utf-8'
    )

    assert 'CurrentVersion\\Uninstall\\ContractLedgerTool' in install_script
    assert 'QuietUninstallString' in install_script
    assert '[switch]$EnableAutostart' in install_script
    assert 'if (-not $NoAutostart)' in install_script
    assert 'if ($EnableAutostart -and -not $NoAutostart)' not in install_script
    assert '--self-check-output' in install_script
    assert '$env:LOCALAPPDATA\\Programs\\ContractLedgerTool' in install_script
    assert 'Refusing to install on the Desktop' in install_script
    assert '$WScriptExe' in install_script
    assert 'launch.vbs' in install_script
    assert 'shell.Run' in install_script
    assert ', 0, False' in install_script
    assert '[System.Security.Cryptography.SHA256]::Create()' in install_script
    assert 'Get-FileHash' not in install_script
    assert '[switch]$RemoveData' in uninstall_script
    assert 'launch.vbs' in uninstall_script
    assert 'Contracts, ledger, templates, settings, and backups were kept' in uninstall_script


def test_offline_binaries_use_windowed_mode_and_hidden_powershell(tmp_path):
    command = _pyinstaller_common.build_pyinstaller_cmd(
        ROOT / 'app.py',
        'ContractLedgerTool',
        tmp_path / 'dist',
        tmp_path / 'work',
        tmp_path / 'spec',
        tmp_path / 'resources',
        windowed=True,
    )
    assert '--windowed' in command
    assert '--console' not in command

    build_script = (ROOT / 'build_installer.py').read_text(encoding='utf-8')
    assert "windowed=True" in build_script
    assert "'--windowed'" in build_script
    assert "'--console'" not in build_script
    assert "CREATE_NO_WINDOW" in build_script
    assert "MessageBoxW" in build_script


def test_windowed_installer_reports_the_resolved_local_url(tmp_path):
    import build_installer

    bootstrap_path = tmp_path / 'offline_installer_bootstrap.py'
    build_installer.write_bootstrap(bootstrap_path)
    spec = importlib.util.spec_from_file_location('installer_bootstrap_test', bootstrap_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._installed_url(
        b'Local URL:         http://127.0.0.1:5007/\r\n',
        '5000',
    ) == 'http://127.0.0.1:5007/'
    assert module._installed_url(b'no url in output', '5050') == (
        'http://127.0.0.1:5050/'
    )
    assert Path(module._default_install_dir()).parts[-2:] == (
        'Programs', 'ContractLedgerTool'
    )

    bootstrap = bootstrap_path.read_text(encoding='utf-8')
    assert 'def _choose_install_dir' in bootstrap
    assert 'from tkinter import filedialog, messagebox, ttk' in bootstrap
    assert "arguments.extend(['-InstallDir', install_dir])" in bootstrap
    assert "f'安装位置：{install_dir}'" in bootstrap


def test_legacy_packaging_commands_delegate_to_graphical_installer():
    desktop_builder = (ROOT / 'build_desktop_exe.py').read_text(encoding='utf-8')
    package_builder = (ROOT / 'build_package.py').read_text(encoding='utf-8')

    assert 'build_installer.main()' in desktop_builder
    assert 'ContractLedgerTool_Setup_v{version}.exe' in desktop_builder
    assert 'build_pyinstaller_cmd' not in desktop_builder
    assert 'from build_desktop_exe import main' in package_builder
    assert 'zipfile' not in package_builder


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
    assert releases[0][0] == version
    datetime.strptime(releases[0][1], '%Y-%m-%d')
    assert len({release_version for release_version, _date in releases}) == len(releases)
