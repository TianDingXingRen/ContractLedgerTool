# -*- coding: utf-8 -*-
"""Build the graphical offline installer and copy one setup file to Desktop.

This compatibility entry point intentionally does not build a portable app EXE.
Running a portable EXE from Desktop made the writable runtime directories appear
next to it.  The generated setup application installs into a user-selected,
dedicated directory and launches the installed app without a console window.
"""

import os
import shutil
from pathlib import Path

import build_installer
from _pyinstaller_common import project_version


DESKTOP = Path(os.environ['USERPROFILE']) / 'Desktop'


def main():
    build_installer.main()
    source = (
        build_installer.RELEASE_DIR /
        f'{build_installer.INSTALLER_EXE_NAME}.exe'
    )
    if not source.is_file():
        raise FileNotFoundError(f'Installer was not generated at {source}')

    version = project_version()
    destination = DESKTOP / f'ContractLedgerTool_Setup_v{version}.exe'
    shutil.copy2(source, destination)
    size_mb = destination.stat().st_size / (1024 * 1024)

    print('\n' + '=' * 60)
    print('Graphical installer generated:')
    print(destination)
    print(f'Size: {size_mb:.1f} MB')
    print('Double-click it, choose a non-Desktop install directory, then install.')
    print('The installed app and launcher run without a console window.')
    print('=' * 60)


if __name__ == '__main__':
    main()
