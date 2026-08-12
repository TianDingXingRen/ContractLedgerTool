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
