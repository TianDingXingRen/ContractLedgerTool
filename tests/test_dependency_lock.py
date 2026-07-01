from pathlib import Path


def test_requirements_lock_pins_runtime_dependencies():
    root = Path(__file__).resolve().parents[1]
    requirements = (root / 'requirements.txt').read_text(encoding='utf-8')
    lock = (root / 'requirements.lock').read_text(encoding='utf-8')

    for package in ['flask', 'python-docx', 'openpyxl', 'pdfplumber', 'pytesseract']:
        assert package in requirements.lower()
        assert f'{package}==' in lock.lower()

    pinned_lines = [
        line.strip() for line in lock.splitlines()
        if line.strip() and not line.startswith('#')
    ]
    assert pinned_lines
    assert all('==' in line for line in pinned_lines)
    assert all('>=' not in line and '<' not in line for line in pinned_lines)
