import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer test')
def test_failed_installer_self_check_restores_previous_program_files(tmp_path):
    root = Path(__file__).resolve().parents[1]
    package_dir = tmp_path / 'package'
    install_dir = tmp_path / 'installed'
    package_dir.mkdir()
    install_dir.mkdir()

    shutil.copy2(root / 'installer_assets' / 'install.ps1', package_dir / 'install.ps1')
    shutil.copy2(
        Path(os.environ['SystemRoot']) / 'System32' / 'where.exe',
        package_dir / 'ContractLedgerTool.exe',
    )

    previous_exe = b'previous-contract-tool-executable'
    previous_launcher = b'previous-start-script'
    (install_dir / 'ContractLedgerTool.exe').write_bytes(previous_exe)
    (install_dir / 'start.ps1').write_bytes(previous_launcher)
    (install_dir / '.contract-ledger-tool-install').write_text(
        'ContractLedgerTool', encoding='ascii',
    )

    completed = subprocess.run(
        [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(package_dir / 'install.ps1'),
            '-InstallDir',
            str(install_dir),
            '-NoDesktopShortcut',
            '-NoAutostart',
            '-NoStart',
            '-SkipSystemIntegrationCleanup',
            '-Port',
            '65431',
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=60,
        check=False,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert 'restoring previous version' in output
    assert 'Previous application files were restored.' in output
    assert (install_dir / 'ContractLedgerTool.exe').read_bytes() == previous_exe
    assert (install_dir / 'start.ps1').read_bytes() == previous_launcher
    assert not (install_dir / 'ContractLedgerTool.exe.new').exists()
    assert not (install_dir / 'ContractLedgerTool.exe.previous').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer test')
def test_offline_installer_refuses_unrecognized_nonempty_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    package_dir = tmp_path / 'package'
    install_dir = tmp_path / 'ordinary-project'
    package_dir.mkdir()
    install_dir.mkdir()

    shutil.copy2(root / 'installer_assets' / 'install.ps1', package_dir / 'install.ps1')
    shutil.copy2(
        Path(os.environ['SystemRoot']) / 'System32' / 'where.exe',
        package_dir / 'ContractLedgerTool.exe',
    )
    source_dir = install_dir / 'core'
    source_dir.mkdir()
    protected_file = source_dir / 'keep.py'
    protected_file.write_text('must not be deleted', encoding='utf-8')
    protected_exe = install_dir / 'ContractLedgerTool.exe'
    protected_exe.write_bytes(b'ordinary same-name executable')
    (install_dir / 'app.py').write_text('ordinary project', encoding='utf-8')
    (install_dir / 'start.ps1').write_text('ordinary launcher', encoding='utf-8')
    (install_dir / 'setup_autostart.ps1').write_text('ordinary setup', encoding='utf-8')
    (install_dir / 'version.txt').write_text('not-an-install', encoding='utf-8')
    (install_dir / '.contract-ledger-tool-install').write_text(
        'unrelated project marker', encoding='utf-8'
    )
    (install_dir / '.venv').mkdir()
    (install_dir / 'data').mkdir()

    completed = subprocess.run(
        [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(package_dir / 'install.ps1'),
            '-InstallDir',
            str(install_dir),
            '-NoDesktopShortcut',
            '-NoAutostart',
            '-NoStart',
            '-SkipSystemIntegrationCleanup',
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=30,
        check=False,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert 'not empty and is not a recognized ContractLedgerTool installation' in output
    assert protected_file.read_text(encoding='utf-8') == 'must not be deleted'
    assert protected_exe.read_bytes() == b'ordinary same-name executable'


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer test')
def test_offline_installer_recognizes_legacy_source_default(tmp_path):
    root = Path(__file__).resolve().parents[1]
    package_dir = tmp_path / 'package'
    local_app_data = tmp_path / 'local-app-data'
    install_dir = local_app_data / 'ContractLedgerTool'
    package_dir.mkdir()
    install_dir.mkdir(parents=True)

    shutil.copy2(root / 'installer_assets' / 'install.ps1', package_dir / 'install.ps1')
    shutil.copy2(
        Path(os.environ['SystemRoot']) / 'System32' / 'where.exe',
        package_dir / 'ContractLedgerTool.exe',
    )
    (install_dir / 'app.py').write_text('legacy app', encoding='utf-8')
    (install_dir / 'start.ps1').write_text('legacy launcher', encoding='utf-8')
    (install_dir / 'setup_autostart.ps1').write_text(
        'legacy setup', encoding='utf-8'
    )
    (install_dir / 'version.txt').write_text('1.5.0', encoding='utf-8')
    (install_dir / '.venv').mkdir()
    (install_dir / 'data').mkdir()

    env = os.environ.copy()
    env['LOCALAPPDATA'] = str(local_app_data)
    completed = subprocess.run(
        [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(package_dir / 'install.ps1'),
            '-InstallDir',
            str(install_dir),
            '-NoDesktopShortcut',
            '-NoAutostart',
            '-NoStart',
            '-SkipSystemIntegrationCleanup',
            '-Port',
            '65432',
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=60,
        check=False,
        env=env,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert 'not empty and is not a recognized' not in output
    assert 'restoring previous version' in output
    assert (install_dir / 'app.py').read_text(encoding='utf-8') == 'legacy app'
    assert (install_dir / 'start.ps1').read_text(encoding='utf-8') == 'legacy launcher'


@pytest.mark.skipif(os.name != 'nt', reason='Windows uninstaller test')
def test_uninstaller_refuses_same_name_executable_without_install_ownership(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ordinary_dir = tmp_path / 'ordinary-project'
    ordinary_dir.mkdir()
    (ordinary_dir / 'ContractLedgerTool.exe').write_bytes(b'unrelated executable')
    sentinel = ordinary_dir / 'keep.txt'
    sentinel.write_text('must survive', encoding='utf-8')

    completed = subprocess.run(
        [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(root / 'installer_assets' / 'uninstall.ps1'),
            '-InstallDir',
            str(ordinary_dir),
            '-RemoveData',
            '-NoPrompt',
            '-SkipSystemIntegrationCleanup',
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=30,
        check=False,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert 'Refusing to uninstall an unrecognized ContractLedgerTool directory' in output
    assert sentinel.read_text(encoding='utf-8') == 'must survive'


@pytest.mark.skipif(os.name != 'nt', reason='Windows uninstaller test')
def test_uninstaller_remove_data_accepts_owned_temporary_install(tmp_path):
    root = Path(__file__).resolve().parents[1]
    install_dir = tmp_path / 'owned-install'
    install_dir.mkdir()
    (install_dir / 'ContractLedgerTool.exe').write_bytes(b'installed executable')
    (install_dir / '.contract-ledger-tool-install').write_text(
        'ContractLedgerTool', encoding='ascii'
    )
    (install_dir / 'data').mkdir()
    (install_dir / 'data' / 'sentinel.db').write_bytes(b'data')

    completed = subprocess.run(
        [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(root / 'installer_assets' / 'uninstall.ps1'),
            '-InstallDir',
            str(install_dir),
            '-RemoveData',
            '-NoPrompt',
            '-SkipSystemIntegrationCleanup',
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not install_dir.exists()


def test_registered_uninstaller_targets_the_exact_install_directory():
    root = Path(__file__).resolve().parents[1]
    install_script = (root / 'installer_assets' / 'install.ps1').read_text(
        encoding='utf-8'
    )
    uninstall_script = (root / 'installer_assets' / 'uninstall.ps1').read_text(
        encoding='utf-8'
    )

    assert '-InstallDir `"$InstallDir`"' in install_script
    assert '[string]$InstallDir = $PSScriptRoot' in uninstall_script
