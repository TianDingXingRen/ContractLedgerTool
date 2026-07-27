import subprocess
from types import SimpleNamespace

import pytest

import pdf_exporter


def _valid_pdf(path):
    path.write_bytes(b'%PDF-1.7\n%%EOF')
    return str(path)


def test_convert_rejects_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        pdf_exporter.convert_docx_to_pdf(tmp_path / 'missing.docx')


def test_find_winword_and_diagnostics(monkeypatch):
    monkeypatch.setattr(
        pdf_exporter.os.path,
        'isfile',
        lambda path: str(path) == pdf_exporter.WINWORD_PATHS[1],
    )
    assert pdf_exporter._find_winword() == pdf_exporter.WINWORD_PATHS[1]
    details = pdf_exporter._diagnose_com_error()
    assert pdf_exporter.WINWORD_PATHS[1] in details
    assert 'Python' in details

    monkeypatch.setattr(pdf_exporter.os.path, 'isfile', lambda _path: False)
    assert pdf_exporter._find_winword() is None
    assert 'Word' in pdf_exporter._diagnose_com_error()


def test_convert_prefers_word_and_validates_output(tmp_path, monkeypatch):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'docx')
    output = tmp_path / 'output.pdf'
    monkeypatch.setattr(
        pdf_exporter,
        '_convert_via_word_com',
        lambda _source, target: _valid_pdf(type(output)(target)),
    )
    monkeypatch.setattr(
        pdf_exporter,
        '_convert_via_libreoffice',
        lambda *_: pytest.fail('LibreOffice fallback should not run'),
    )
    assert pdf_exporter.convert_docx_to_pdf(source, output) == str(output)


def test_convert_falls_back_to_libreoffice(tmp_path, monkeypatch):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'docx')
    output = tmp_path / 'output.pdf'
    monkeypatch.setattr(
        pdf_exporter, '_convert_via_word_com',
        lambda *_: (_ for _ in ()).throw(RuntimeError('COM unavailable')),
    )
    monkeypatch.setattr(
        pdf_exporter,
        '_convert_via_libreoffice',
        lambda _source, target: _valid_pdf(type(output)(target)),
    )
    assert pdf_exporter.convert_docx_to_pdf(source, output) == str(output)


def test_libreoffice_converter_not_found(tmp_path, monkeypatch):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'docx')
    monkeypatch.setattr(pdf_exporter.os.path, 'isfile', lambda _path: False)
    monkeypatch.setattr('shutil.which', lambda _name: None)
    with pytest.raises(RuntimeError):
        pdf_exporter._convert_via_libreoffice(str(source), str(tmp_path / 'out.pdf'))


def test_libreoffice_converter_renames_generated_file(tmp_path, monkeypatch):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'docx')
    target = tmp_path / 'renamed.pdf'
    expected = tmp_path / 'source.pdf'
    run_kwargs = {}
    monkeypatch.setattr('shutil.which', lambda name: name if name == 'soffice' else None)

    def fake_run(_args, **kwargs):
        run_kwargs.update(kwargs)
        _valid_pdf(expected)
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(pdf_exporter.subprocess, 'run', fake_run)
    assert pdf_exporter._convert_via_libreoffice(str(source), str(target)) == str(target)
    assert target.is_file()
    assert not expected.exists()
    if pdf_exporter.os.name == 'nt':
        assert run_kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW
        assert (
            run_kwargs['startupinfo'].dwFlags
            & subprocess.STARTF_USESHOWWINDOW
        )


def test_libreoffice_converter_reports_process_failure_and_timeout(tmp_path, monkeypatch):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'docx')
    target = tmp_path / 'out.pdf'
    monkeypatch.setattr('shutil.which', lambda name: name if name == 'soffice' else None)
    monkeypatch.setattr(
        pdf_exporter.subprocess,
        'run',
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout='', stderr='bad input'),
    )
    with pytest.raises(RuntimeError, match='bad input'):
        pdf_exporter._convert_via_libreoffice(str(source), str(target))

    monkeypatch.setattr(
        pdf_exporter.subprocess,
        'run',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired('soffice', 60)),
    )
    with pytest.raises(RuntimeError):
        pdf_exporter._convert_via_libreoffice(str(source), str(target))


def test_libreoffice_converter_reports_missing_expected_output(tmp_path, monkeypatch):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'docx')
    target = tmp_path / 'out.pdf'
    monkeypatch.setattr('shutil.which', lambda name: name if name == 'soffice' else None)
    monkeypatch.setattr(
        pdf_exporter.subprocess,
        'run',
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout='ok', stderr=''),
    )
    with pytest.raises(RuntimeError):
        pdf_exporter._convert_via_libreoffice(str(source), str(target))


def test_pdf_validator_rejects_missing_and_header_only_files(tmp_path):
    with pytest.raises(RuntimeError):
        pdf_exporter._validate_pdf_output(tmp_path / 'missing.pdf')
    header_only = tmp_path / 'header-only.pdf'
    header_only.write_bytes(pdf_exporter.PDF_HEADER)
    with pytest.raises(RuntimeError):
        pdf_exporter._validate_pdf_output(header_only)


def test_environment_diagnostics(monkeypatch):
    monkeypatch.setattr(pdf_exporter, '_find_winword', lambda: 'C:/Office/WINWORD.EXE')
    monkeypatch.setattr(pdf_exporter.os.path, 'isfile', lambda path: 'WINWORD' in str(path))
    monkeypatch.setattr('shutil.which', lambda name: 'C:/LibreOffice/soffice.exe' if name == 'soffice' else None)
    monkeypatch.setattr(pdf_exporter, 'find_spec', lambda name: object() if name == 'win32com' else None)
    info = pdf_exporter.diagnose_environment()
    assert info['winword_found'] == 'C:/Office/WINWORD.EXE'
    assert info['libreoffice_found'] == 'True'
    assert info['pywin32'] == 'installed'
    assert info['pythoncom'] == 'not available'


def test_environment_diagnostics_without_converters(monkeypatch):
    monkeypatch.setattr(pdf_exporter, '_find_winword', lambda: None)
    monkeypatch.setattr(pdf_exporter.os.path, 'isfile', lambda _path: False)
    monkeypatch.setattr('shutil.which', lambda _name: None)
    monkeypatch.setattr(pdf_exporter, 'find_spec', lambda _name: None)
    info = pdf_exporter.diagnose_environment()
    assert info['winword_found'] == 'Not found'
    assert info['libreoffice_found'] == 'False'
    assert info['winword_paths_checked'] == '(none found)'


def test_terminate_word_process_handles_running_process(monkeypatch):
    calls = []
    run_kwargs = {}

    class FakeProcess:
        pid = 4321

        @staticmethod
        def poll():
            return None

        @staticmethod
        def terminate():
            calls.append('terminate')

        @staticmethod
        def wait(timeout):
            calls.append(('wait', timeout))

    monkeypatch.setattr(
        pdf_exporter.subprocess, 'run',
        lambda args, **kwargs: (
            run_kwargs.update(kwargs)
            or calls.append(args)
            or SimpleNamespace(returncode=0)
        ),
    )
    pdf_exporter._terminate_word_proc(FakeProcess())
    assert calls[0] == 'terminate'
    assert calls[-1][-1] == '4321'
    if pdf_exporter.os.name == 'nt':
        assert run_kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW
        assert (
            run_kwargs['startupinfo'].dwFlags
            & subprocess.STARTF_USESHOWWINDOW
        )
    pdf_exporter._terminate_word_proc(None)


def test_terminate_word_process_kills_after_wait_timeout(monkeypatch):
    calls = []

    class StuckProcess:
        pid = 9876

        @staticmethod
        def poll():
            return None

        @staticmethod
        def terminate():
            calls.append('terminate')

        @staticmethod
        def wait(timeout):
            raise subprocess.TimeoutExpired('WINWORD', timeout)

        @staticmethod
        def kill():
            calls.append('kill')

    monkeypatch.setattr(
        pdf_exporter.subprocess, 'run',
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    pdf_exporter._terminate_word_proc(StuckProcess())
    assert calls == ['terminate', 'kill']
