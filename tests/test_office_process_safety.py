import inspect
import queue

import pytest

import pdf_exporter
from services import isolated_process, legacy_doc_conversion_service


def test_isolated_worker_timeout_terminates_process(monkeypatch):
    calls = []

    class FakeQueue:
        def get(self, timeout):
            assert timeout > 0
            raise queue.Empty

        def close(self):
            calls.append('queue-close')

        def join_thread(self):
            calls.append('queue-join')

    class FakeProcess:
        exitcode = None

        def __init__(self):
            self.running = True

        def start(self):
            calls.append('start')

        def join(self, timeout):
            calls.append(('join', timeout))

        def is_alive(self):
            return self.running

        def terminate(self):
            calls.append('terminate')
            self.running = False

    process = FakeProcess()

    class FakeContext:
        def Queue(self, maxsize):
            assert maxsize == 1
            return FakeQueue()

        def Process(self, **_kwargs):
            return process

    monkeypatch.setattr(isolated_process.multiprocessing, 'get_context', lambda _name: FakeContext())
    with pytest.raises(RuntimeError, match='超时'):
        isolated_process.run_isolated_worker(
            lambda: None, (), timeout=1, label='Office test',
        )
    assert 'terminate' in calls
    assert 'queue-close' in calls


def test_legacy_conversion_removes_partial_output_on_failure(tmp_path, monkeypatch):
    source = tmp_path / 'source.doc'
    target = tmp_path / 'source.docx'
    source.write_bytes(b'legacy')

    def fail_worker(_worker, args, **_kwargs):
        args[1].write_bytes(b'partial') if hasattr(args[1], 'write_bytes') else target.write_bytes(b'partial')
        raise RuntimeError('conversion failed')

    monkeypatch.setattr(legacy_doc_conversion_service, 'run_isolated_worker', fail_worker)
    with pytest.raises(RuntimeError, match='conversion failed'):
        legacy_doc_conversion_service.convert_doc_to_docx(source, target)
    assert not target.exists()


def test_legacy_conversion_rejects_unrelated_target_path(tmp_path):
    source = tmp_path / 'source.doc'
    source.write_bytes(b'legacy')

    with pytest.raises(ValueError, match='目标路径无效'):
        legacy_doc_conversion_service.convert_doc_to_docx(
            source, tmp_path / 'other.docx'
        )


def test_word_workers_use_isolated_instances_and_disable_macros():
    pdf_source = inspect.getsource(pdf_exporter._word_pdf_worker)
    doc_source = inspect.getsource(legacy_doc_conversion_service._legacy_doc_worker)
    assert 'DispatchEx' in pdf_source
    assert 'AutomationSecurity = 3' in pdf_source
    assert 'DispatchEx' in doc_source
    assert 'AutomationSecurity = 3' in doc_source
