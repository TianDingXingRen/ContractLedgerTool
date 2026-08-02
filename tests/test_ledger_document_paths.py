import os
import sqlite3

from ledger_store import document_paths


def test_runtime_owned_path_is_stored_portably_and_resolved(tmp_path):
    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    document = output_dir / 'generated.docx'
    document.write_bytes(b'docx')

    stored = document_paths.to_portable(str(document), str(tmp_path))

    assert stored == 'output/generated.docx'
    assert document_paths.resolve(stored, str(tmp_path)) == str(document)


def test_missing_legacy_absolute_output_path_rebases_to_current_runtime(tmp_path):
    legacy = os.path.join(
        str(tmp_path), 'retired-runtime', 'output', 'generated.docx'
    )

    assert document_paths.resolve(legacy, str(tmp_path)) == str(
        tmp_path / 'output' / 'generated.docx'
    )


def test_external_absolute_path_remains_absolute(tmp_path):
    external = os.path.abspath(os.path.join(str(tmp_path), '..', 'external.docx'))

    assert document_paths.to_portable(external, str(tmp_path)) == external
    assert document_paths.resolve(external, str(tmp_path)) == external


def test_normalize_contract_paths_reports_updated_rows(tmp_path):
    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    document = output_dir / 'generated.docx'
    document.write_bytes(b'docx')
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE contracts (id INTEGER PRIMARY KEY, docx_path TEXT)')
    conn.execute(
        'INSERT INTO contracts (docx_path) VALUES (?)',
        (str(document),),
    )

    updated = document_paths.normalize_contract_paths(conn, str(tmp_path))
    stored = conn.execute('SELECT docx_path FROM contracts').fetchone()['docx_path']
    conn.close()

    assert updated == 1
    assert stored == 'output/generated.docx'
