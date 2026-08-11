from pathlib import Path
import json
import re


def test_requirements_lock_pins_runtime_dependencies():
    root = Path(__file__).resolve().parents[1]
    requirements = (root / 'requirements.txt').read_text(encoding='utf-8')
    lock = (root / 'requirements.lock').read_text(encoding='utf-8')

    for package in ['flask', 'python-docx', 'openpyxl', 'pdfplumber', 'pytesseract']:
        assert package in requirements.lower()
        assert f'{package}==' in lock.lower()

    entries = re.findall(
        r'(?ms)^([A-Za-z0-9][A-Za-z0-9_.-]*==[^\n]+)'
        r'(.*?)(?=^[A-Za-z0-9][A-Za-z0-9_.-]*==|\Z)',
        lock,
    )
    assert entries
    assert all('>=' not in requirement and '<' not in requirement
               for requirement, _details in entries)
    assert all('--hash=sha256:' in details for _requirement, details in entries)


def _numeric_version(value):
    return tuple(int(part) for part in value.split('.'))


def test_security_remediation_versions_are_locked():
    root = Path(__file__).resolve().parents[1]
    runtime_lock = (root / 'requirements.lock').read_text(encoding='utf-8')
    development_lock = (root / 'requirements-dev.lock').read_text(encoding='utf-8')
    cryptography = re.search(
        r'^cryptography==([^\s\\]+)',
        runtime_lock,
        flags=re.MULTILINE,
    )
    assert cryptography
    assert _numeric_version(cryptography.group(1)) >= (50, 0, 0)

    setuptools = re.search(
        r'^setuptools==([^\s\\]+)',
        development_lock,
        flags=re.MULTILINE,
    )
    assert setuptools
    assert _numeric_version(setuptools.group(1)) >= (83, 0, 0)

    npm_lock = json.loads((root / 'package-lock.json').read_text(encoding='utf-8'))
    packages = npm_lock['packages']
    assert _numeric_version(packages['node_modules/nanoid']['version']) >= (3, 3, 17)
    assert _numeric_version(packages['node_modules/postcss']['version']) >= (8, 5, 23)
