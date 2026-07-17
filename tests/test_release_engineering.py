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
    assert 'gh release create' in release
    assert 'CODESIGN_' not in release


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
