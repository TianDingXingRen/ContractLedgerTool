from pathlib import Path
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
