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
