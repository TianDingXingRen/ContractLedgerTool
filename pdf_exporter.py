"""Convert .docx to .pdf using Word COM (Windows only) with LibreOffice fallback.

Falls back gracefully if Word is not installed or COM is unavailable.
COM calls run in a thread with a 30-second timeout to prevent blocking.
"""

import os
import subprocess
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from importlib.util import find_spec

_log = logging.getLogger('contract_tool')

COM_TIMEOUT = 30  # 秒
PDF_HEADER = b'%PDF-'


_WINWORD_PATHS = [
    r'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE',
    r'C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE',
    r'C:\Program Files\Microsoft Office\root\Office15\WINWORD.EXE',
    r'C:\Program Files (x86)\Microsoft Office\root\Office15\WINWORD.EXE',
]

WINWORD_PATHS = _WINWORD_PATHS


def _find_winword():
    for p in _WINWORD_PATHS:
        if os.path.isfile(p):
            return p
    return None


def _diagnose_com_error():
    """Provide specific diagnostics for COM failures."""
    messages = []
    winword = _find_winword()
    if not winword:
        messages.append('Microsoft Word 未安装或未在标准路径找到。')
    else:
        messages.append(f'Word 可执行文件: {winword}')
        # Try to detect Word bitness vs Python bitness
        python_bits = '64-bit' if sys.maxsize > 2**32 else '32-bit'
        messages.append(f'Python 架构: {python_bits}')

    messages.append('可能的原因：')
    messages.append('1. Office 即点即用(C2R)虚拟化环境阻止了 COM 启动。')
    messages.append('2. 尝试修复：打开 Word 一次以初始化 C2R 环境。')
    messages.append('3. 尝试以管理员身份运行本程序。')
    messages.append('4. 或安装 pywin32 (pip install pywin32)。')
    return '\n'.join(messages)


def convert_docx_to_pdf(docx_path, pdf_path=None):
    """Convert a .docx file to .pdf — Word COM 优先，LibreOffice 兜底。

    Returns the pdf_path on success, or raises RuntimeError with diagnostics.
    COM 操作在后台线程执行，最多等待 COM_TIMEOUT 秒。
    """
    if pdf_path is None:
        pdf_path = os.path.splitext(docx_path)[0] + '.pdf'

    abs_docx = os.path.abspath(docx_path)
    abs_pdf = os.path.abspath(pdf_path)

    if not os.path.isfile(abs_docx):
        raise FileNotFoundError(f'源文件不存在: {abs_docx}')

    # 优先尝试 Word COM
    try:
        result = _convert_via_word_com(abs_docx, abs_pdf)
        return _validate_pdf_output(result)
    except (ImportError, RuntimeError) as word_err:
        _log.warning('Word COM 转换失败，尝试 LibreOffice 回退: %s', word_err)

    # 回退：LibreOffice headless
    result = _convert_via_libreoffice(abs_docx, abs_pdf)
    return _validate_pdf_output(result)


def _validate_pdf_output(path):
    """Ensure external converters actually produced a non-empty PDF."""
    if not path or not os.path.isfile(path):
        raise RuntimeError('PDF 转换未生成输出文件')
    with open(path, 'rb') as stream:
        header = stream.read(len(PDF_HEADER))
    if header != PDF_HEADER or os.path.getsize(path) <= len(PDF_HEADER):
        raise RuntimeError('PDF 转换输出无效')
    return path


def _convert_via_libreoffice(docx_path, pdf_path):
    """使用 LibreOffice --headless 模式转换 DOCX → PDF"""
    import shutil
    out_dir = os.path.dirname(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    lo_paths = [
        'soffice',
        'libreoffice',
        r'C:\Program Files\LibreOffice\program\soffice.exe',
        r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    ]
    soffice = None
    for p in lo_paths:
        if os.path.isabs(p) and os.path.isfile(p):
            soffice = p
            break
        elif not os.path.isabs(p) and shutil.which(p):
            soffice = p
            break

    if not soffice:
        raise RuntimeError(
            'PDF 导出失败：未找到 Word 或 LibreOffice。\n'
            '请安装 LibreOffice (https://www.libreoffice.org) 或 Microsoft Word。'
        )

    try:
        result = subprocess.run(
            [soffice, '--headless', '--convert-to', 'pdf',
             '--outdir', out_dir, docx_path],
            timeout=60, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f'LibreOffice 转换失败: {result.stderr.strip() or result.stdout.strip()}')
        # soffice 输出文件名 = 原文件名(.docx → .pdf)
        expected = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + '.pdf')
        if expected != pdf_path and os.path.isfile(expected):
            os.replace(expected, pdf_path)
        if not os.path.isfile(pdf_path):
            raise RuntimeError('LibreOffice 未生成预期的 PDF 文件')
    except subprocess.TimeoutExpired:
        raise RuntimeError('LibreOffice PDF 导出超时（60秒）')

    return pdf_path


def _convert_via_word_com(docx_path, pdf_path):
    """通过 Word COM 执行转换（原 convert_docx_to_pdf 核心逻辑）"""
    # ── 预检（主线程快速完成） ──
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        raise RuntimeError(
            'PDF 导出需要安装 pywin32 (pip install pywin32)\n' + _diagnose_com_error()
        )

    winword = _find_winword()
    if not winword:
        raise RuntimeError(
            '未检测到 Microsoft Word 安装。PDF 导出需要安装 Word 2013 或更高版本。'
        )

    # ── 在线程中执行 COM 操作，防止阻塞主请求线程 ──
    # 用可变容器跟踪 Word 进程，以便超时时清理
    _state = {'word_proc': None, 'last_error': None}

    def _com_convert():
        pythoncom.CoInitialize()
        word = None
        try:
            # 尝试多种方式连接 Word COM
            for _method_name, method in [
                ('Dispatch', lambda: win32com.client.Dispatch('Word.Application')),
                ('DispatchEx', lambda: win32com.client.DispatchEx('Word.Application')),
                ('GetActiveObject', lambda: win32com.client.GetActiveObject('Word.Application')),
            ]:
                try:
                    word = method()
                    break
                except Exception as e:
                    _state['last_error'] = e
                    continue

            if word is None:
                try:
                    _state['word_proc'] = subprocess.Popen(
                        [winword, '/embedding', '/q'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(5)
                    for _method_name, method in [
                        ('GetActiveObject after launch', lambda: win32com.client.GetActiveObject('Word.Application')),
                        ('Dispatch after launch', lambda: win32com.client.Dispatch('Word.Application')),
                        ('DispatchEx after launch', lambda: win32com.client.DispatchEx('Word.Application')),
                    ]:
                        try:
                            word = method()
                            break
                        except Exception as e:
                            _state['last_error'] = e
                            continue
                except Exception as e:
                    _state['last_error'] = e

            if word is None:
                raise RuntimeError(
                    f'无法启动 Microsoft Word COM 服务。\n\n{_diagnose_com_error()}\n\n'
                    f'最后错误: {_state["last_error"]}'
                )

            word.Visible = False
            word.DisplayAlerts = 0

            doc = word.Documents.Open(docx_path)
            try:
                doc.SaveAs2(pdf_path, FileFormat=17)  # wdFormatPDF = 17
            finally:
                try:
                    doc.Close()
                except Exception:
                    _log.debug('Word COM doc.Close 失败', exc_info=True)
        finally:
            if word:
                try:
                    word.Quit()
                except Exception:
                    _log.debug('Word COM Quit 失败', exc_info=True)
            pythoncom.CoUninitialize()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_com_convert)
        try:
            future.result(timeout=COM_TIMEOUT)
        except FutureTimeoutError:
            _terminate_word_proc(_state['word_proc'])
            raise RuntimeError(
                f'PDF 导出超时（{COM_TIMEOUT} 秒）。\n'
                '请关闭其他 Word 窗口和对话框后重试。\n\n'
                + _diagnose_com_error()
            )
        except Exception:
            _terminate_word_proc(_state['word_proc'])
            raise

    return pdf_path


def _terminate_word_proc(proc):
    """尝试终止由 subprocess.Popen 启动的 Word 进程。

    注意：仅处理 Popen 启动的进程，不影响用户自己的 Word 窗口。
    COM Dispatch 方式启动的 Word 由 word.Quit() 在 finally 块中处理。

    若 terminate 失败，使用 taskkill 做最终兜底。
    """
    if proc is None:
        return
    pid = proc.pid
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                _log.warning('Word 进程强制终止（仅影响本工具启动的 Word 实例）')
    except Exception:
        _log.debug('Word 进程清理失败', exc_info=True)
    # taskkill 兜底：确保进程树被彻底清理
    if pid is not None:
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True, timeout=10,
            )
        except Exception:
            _log.debug('taskkill 清理失败', exc_info=True)


def diagnose_environment() -> dict[str, str]:
    """Return diagnostic info about the PDF conversion environment."""
    import shutil
    info = {
        'platform': sys.platform,
        'python_bits': '64-bit' if sys.maxsize > 2**32 else '32-bit',
        'python_version': sys.version.split()[0],
    }
    winword = _find_winword()
    info['winword_found'] = str(winword) if winword else 'Not found'
    lo_found = any(
        (os.path.isabs(p) and os.path.isfile(p)) or shutil.which(p)
        for p in ['soffice', 'libreoffice']
    )
    info['libreoffice_found'] = str(lo_found)
    info['pywin32'] = 'installed' if find_spec('win32com') else 'not installed'
    info['pythoncom'] = 'available' if find_spec('pythoncom') else 'not available'
    info['winword_paths_checked'] = ', '.join(
        p for p in _WINWORD_PATHS if os.path.isfile(p)
    ) or '(none found)'
    return info
