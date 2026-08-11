import importlib.util
import os
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
    runtime_lock = (ROOT / 'requirements.lock').read_text(encoding='utf-8')
    entry_pattern = re.compile(
        r'(?ms)^([A-Za-z0-9][A-Za-z0-9_.-]*==[^\n]+)'
        r'(.*?)(?=^[A-Za-z0-9][A-Za-z0-9_.-]*==|\Z)'
    )
    entries = entry_pattern.findall(lock)
    runtime_entries = entry_pattern.findall(runtime_lock)
    pinned_names = {
        requirement.split('==', 1)[0].lower()
        for requirement, _details in entries
    }
    runtime_names = {
        requirement.split('==', 1)[0].lower()
        for requirement, _details in runtime_entries
    }
    assert runtime_names <= pinned_names
    assert {'pytest', 'ruff', 'pytest-cov', 'playwright', 'pyinstaller'} <= {
        name.lower() for name in pinned_names
    }
    assert all(
        requirement.split(';', 1)[0].count('==') == 1
        and '--hash=sha256:' in details
        for requirement, details in entries
    )


def test_ci_and_release_workflows_use_the_shared_quality_gate():
    ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    release = (
        ROOT / '.github' / 'workflows' / 'release.yml'
    ).read_text(encoding='utf-8')

    assert 'python scripts/quality_gate.py ci' in ci
    assert 'requirements-dev.lock' in ci
    assert 'playwright install chromium' in ci
    assert 'build/coverage.xml' in ci
    dev_audit = (
        'python -m pip_audit -r requirements-dev.lock '
        '--no-deps --disable-pip'
    )
    assert dev_audit in ci
    assert 'npm audit --audit-level=moderate' in ci

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
    assert dev_audit in release
    assert 'npm audit --audit-level=moderate' in release

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

    build_script = (ROOT / 'build_package.py').read_text(encoding='utf-8')
    assert "windowed=True" in build_script
    assert "'--windowed'" in build_script
    assert "'--console'" not in build_script
    assert "CREATE_NO_WINDOW" in build_script
    assert "MessageBoxW" in build_script


def test_windowed_installer_reports_the_resolved_local_url(tmp_path):
    import build_package

    bootstrap_path = tmp_path / 'offline_installer_bootstrap.py'
    build_package.write_bootstrap(bootstrap_path)
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


def test_windowed_installer_leaves_desktop_before_opening_picker(
        tmp_path, monkeypatch):
    import build_package

    bootstrap_path = tmp_path / 'offline_installer_bootstrap.py'
    build_package.write_bootstrap(bootstrap_path)
    spec = importlib.util.spec_from_file_location(
        'installer_bootstrap_workdir_test',
        bootstrap_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    launch_dir = tmp_path / 'simulated-desktop'
    payload_dir = tmp_path / 'private-payload'
    launch_dir.mkdir()
    payload_dir.mkdir()
    observed = {}

    monkeypatch.setattr(module, '_payload_root', lambda: payload_dir)
    monkeypatch.setattr(module, '_message_box', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, '_desktop_dir', lambda: launch_dir)

    def cancel_picker(default):
        observed['cwd'] = Path.cwd()
        return None

    monkeypatch.setattr(module, '_choose_install_dir', cancel_picker)
    monkeypatch.setattr(module.sys, 'argv', ['installer.exe'])

    previous = Path.cwd()
    try:
        os.chdir(launch_dir)
        assert module.main() == 0
    finally:
        os.chdir(previous)

    assert observed['cwd'] == payload_dir.resolve()
    assert list(launch_dir.iterdir()) == []


def test_windowed_installer_removes_only_fresh_empty_desktop_log(
        tmp_path, monkeypatch):
    import build_package

    bootstrap_path = tmp_path / 'offline_installer_bootstrap.py'
    build_package.write_bootstrap(bootstrap_path)
    spec = importlib.util.spec_from_file_location(
        'installer_bootstrap_cleanup_test',
        bootstrap_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_desktop_dir', lambda: tmp_path)

    started_at = module.time.time() - 1
    fresh_empty = tmp_path / 'log'
    fresh_empty.mkdir()
    assert module._remove_fresh_empty_desktop_log(started_at) is True
    assert not fresh_empty.exists()

    existing_empty = tmp_path / 'log'
    existing_empty.mkdir()
    assert module._remove_fresh_empty_desktop_log(
        module.time.time() + 60
    ) is False
    assert existing_empty.is_dir()

    (existing_empty / 'keep.txt').write_text('user data', encoding='utf-8')
    assert module._remove_fresh_empty_desktop_log(started_at) is False
    assert (existing_empty / 'keep.txt').read_text(encoding='utf-8') == 'user data'


def test_installer_uses_early_runtime_working_directory_hook(tmp_path):
    import build_package

    hook_path = tmp_path / 'installer_runtime_hook.py'
    build_package.write_installer_runtime_hook(hook_path)
    hook = hook_path.read_text(encoding='utf-8')
    build_script = (ROOT / 'build_package.py').read_text(encoding='utf-8')

    assert "getattr(sys, '_MEIPASS', None)" in hook
    assert 'os.chdir(runtime_root)' in hook
    assert "'--runtime-hook', str(INSTALLER_RUNTIME_HOOK)" in build_script


def test_packaging_uses_one_argparse_entry_point():
    package_builder = (ROOT / 'build_package.py').read_text(encoding='utf-8')

    assert not (ROOT / 'build_desktop_exe.py').exists()
    assert not (ROOT / 'build_installer.py').exists()
    assert "add_parser('app'" in package_builder
    assert "add_parser('installer'" in package_builder
    assert "'desktop'," in package_builder
    assert 'ContractLedgerTool_Setup_v{project_version()}.exe' in package_builder
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
