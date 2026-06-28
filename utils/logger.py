"""Structured logging: file + console, rotating by date, with sensitive data filtering."""

import logging
import os
import re
import sys
import threading

LOG_DIR = None
_logger = None
_logger_lock = threading.Lock()


class SensitiveDataFilter(logging.Filter):
    """过滤日志中的敏感字段值（合同金额、编号等）"""

    _SENSITIVE_RE = re.compile(
        r'(contract_no|合同编号|amount|金额|account_no|账号|bank|开户行)'
        r'[=:：]\s*["\']?\S*["\']?',
        re.IGNORECASE,
    )

    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._SENSITIVE_RE.sub(r'\1=***', record.msg)
        return True


def setup_logging(log_dir=None, level=logging.INFO):
    global LOG_DIR, _logger
    with _logger_lock:
        LOG_DIR = log_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        os.makedirs(LOG_DIR, exist_ok=True)

        fmt = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        _logger = logging.getLogger('contract_tool')
        _logger.setLevel(level)
        _logger.addFilter(SensitiveDataFilter())
        for handler in list(_logger.handlers):
            handler.close()
        _logger.handlers.clear()

        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, 'app.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        _logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(fmt)
        _logger.addHandler(console_handler)

        return _logger


def get_logger():
    with _logger_lock:
        logger = _logger
    if logger is None:
        return setup_logging()
    return logger


def close_logging():
    """关闭文件处理器，供测试重建应用或进程退出时释放 Windows 文件句柄。"""
    global _logger
    with _logger_lock:
        if _logger is None:
            return
        for handler in list(_logger.handlers):
            try:
                handler.flush()
                handler.close()
            finally:
                _logger.removeHandler(handler)
        _logger = None
