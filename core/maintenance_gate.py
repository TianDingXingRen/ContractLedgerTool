"""Coordinate normal web requests with destructive maintenance operations."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


class MaintenanceBusyError(RuntimeError):
    """Raised when another destructive maintenance operation is already pending."""


@dataclass
class _RequestToken:
    active: bool = True


class MaintenanceGate:
    """Allow concurrent requests but give restore/encryption operations exclusivity."""

    def __init__(self):
        self._condition = threading.Condition()
        self._promotion_lock = threading.Lock()
        self._active_requests = 0
        self._maintenance_active = False
        self._current_token: ContextVar[_RequestToken | None] = ContextVar(
            'maintenance_request_token', default=None,
        )

    def enter_request(self):
        with self._condition:
            while self._maintenance_active:
                self._condition.wait()
            token = _RequestToken()
            self._active_requests += 1
        context_token = self._current_token.set(token)
        return token, context_token

    def leave_request(self, token, context_token) -> None:
        try:
            with self._condition:
                if token.active:
                    token.active = False
                    self._active_requests -= 1
                    self._condition.notify_all()
        finally:
            self._current_token.reset(context_token)

    @contextmanager
    def exclusive(self):
        """Wait for existing requests and block new requests until completion."""
        request_token = self._current_token.get()
        if not self._promotion_lock.acquire(blocking=False):
            raise MaintenanceBusyError('已有数据维护操作正在进行，请稍后重试')

        promoted_request = False
        try:
            with self._condition:
                self._maintenance_active = True
                if request_token is not None and request_token.active:
                    request_token.active = False
                    self._active_requests -= 1
                    promoted_request = True
                    self._condition.notify_all()
                while self._active_requests:
                    self._condition.wait()
            yield
        finally:
            with self._condition:
                if promoted_request:
                    request_token.active = True
                    self._active_requests += 1
                self._maintenance_active = False
                self._condition.notify_all()
            self._promotion_lock.release()

    def reset(self) -> None:
        """Reset idle state between isolated application instances in tests."""
        with self._condition:
            if self._active_requests or self._maintenance_active:
                raise RuntimeError('不能在请求或维护操作进行时重置维护锁')
            self._current_token.set(None)


maintenance_gate = MaintenanceGate()
