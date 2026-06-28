# -*- coding: utf-8 -*-
"""Build a single-file Windows executable with PyInstaller."""

import json
import subprocess
import sys
from pathlib import Path

from _pyinstaller_common import (
    ROOT, HIDDEN_IMPORTS, reset_dir, copy_file, copy_html_templates,
    collect_contract_templates, write_version_file, build_pyinstaller_cmd,
)


RES_DIR = ROOT / 'build' / 'exe_resources'
EXE_NAME = 'ContractLedgerTool'


def prepare_resources():
    reset_dir(RES_DIR)
    templates_out = RES_DIR / 'templates'
    uploads_out = RES_DIR / 'uploads'
    static_out = RES_DIR / 'static'
    templates_out.mkdir(parents=True, exist_ok=True)
    uploads_out.mkdir(parents=True, exist_ok=True)

    from _pyinstaller_common import copy_tree
    copy_tree(ROOT / 'static', static_out)

    version_src = ROOT / 'version.txt'
    if version_src.is_file():
        copy_file(version_src, RES_DIR / 'version.txt')

    html_templates = copy_html_templates(templates_out)
    copied_templates, copied_uploads, skipped = collect_contract_templates(templates_out, uploads_out)

    return {
        'html_templates': html_templates,
        'templates': copied_templates,
        'uploads': copied_uploads,
        'skipped': skipped,
    }


def main():
    manifest = prepare_resources()
    dist_path = ROOT / 'dist' / 'exe'
    work_path = ROOT / 'build' / 'pyinstaller'
    spec_path = ROOT / 'build' / 'pyinstaller_spec'
    dist_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    spec_path.mkdir(parents=True, exist_ok=True)

    cmd = build_pyinstaller_cmd(
        ROOT / 'app.py', EXE_NAME, dist_path, work_path, spec_path, RES_DIR,
    )
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe_path = dist_path / f'{EXE_NAME}.exe'
    print(json.dumps({
        'exe': str(exe_path),
        'size_mb': round(exe_path.stat().st_size / 1024 / 1024, 2),
        **manifest,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
