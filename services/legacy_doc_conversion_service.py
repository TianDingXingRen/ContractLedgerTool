"""Convert legacy binary Word documents in an isolated desktop process."""

from __future__ import annotations

import os
import logging

from services.isolated_process import run_isolated_worker
from utils.security import validate_office_archive


DOC_CONVERT_TIMEOUT = 30
_log = logging.getLogger('contract_tool')


def convert_doc_to_docx(doc_path, target_path=None, *, timeout=DOC_CONVERT_TIMEOUT):
    source = os.path.abspath(doc_path)
    target = os.path.abspath(target_path or os.path.splitext(source)[0] + '.docx')
    try:
        run_isolated_worker(
            _legacy_doc_worker, (source, target),
            timeout=timeout, label='DOC 转 DOCX',
        )
        validate_office_archive(target)
        return target
    except Exception:
        try:
            os.remove(target)
        except FileNotFoundError:
            _log.debug('Failed DOCX conversion output already absent: %s', target)
        raise


def _legacy_doc_worker(source, target, result_queue):
    pythoncom = None
    errors = []
    try:
        import pythoncom as _pythoncom
        from win32com import client

        pythoncom = _pythoncom
        pythoncom.CoInitialize()
        for progid in ('Word.Application', 'WPS.Application', 'KWPS.Application'):
            application = None
            document = None
            try:
                application = client.DispatchEx(progid)
                application.Visible = False
                application.DisplayAlerts = 0
                # Do not open untrusted legacy documents unless macros can be
                # force-disabled by the selected Office automation server.
                application.AutomationSecurity = 3
                document = application.Documents.Open(
                    source, ReadOnly=True, AddToRecentFiles=False,
                    ConfirmConversions=False,
                )
                document.SaveAs2(target, FileFormat=16)
                result_queue.put(('ok', target))
                return
            except BaseException as exc:
                errors.append(f'{progid}: {type(exc).__name__}: {exc}')
            finally:
                if document is not None:
                    try:
                        document.Close(SaveChanges=0)
                    except Exception:
                        _log.debug('Legacy document cleanup failed', exc_info=True)
                if application is not None:
                    try:
                        application.Quit(SaveChanges=0)
                    except Exception:
                        _log.debug('Legacy Office application cleanup failed', exc_info=True)
        result_queue.put(('error', '；'.join(errors) or '未找到可用的 Word/WPS 转换器'))
    except BaseException as exc:
        result_queue.put(('error', f'Office 自动化初始化失败：{type(exc).__name__}: {exc}'))
    finally:
        if pythoncom is not None:
            pythoncom.CoUninitialize()
