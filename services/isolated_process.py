"""Run unsafe desktop automation in a hard-time-limited child process."""

from __future__ import annotations

import logging
import multiprocessing
import os
import queue
import time


def _apply_posix_memory_limit(memory_limit_mb):
    if os.name == 'nt' or not memory_limit_mb:
        return
    import resource

    limit = int(memory_limit_mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _worker_entry(worker, args, result_queue, memory_limit_mb):
    try:
        _apply_posix_memory_limit(memory_limit_mb)
        worker(*args, result_queue)
    except BaseException as exc:
        try:
            result_queue.put(
                (
                    'value_error' if isinstance(exc, ValueError) else 'error',
                    str(exc)
                    if isinstance(exc, ValueError)
                    else f'{type(exc).__name__}: {exc}',
                ),
                block=False,
            )
        except BaseException:
            logging.getLogger('contract_tool').exception(
                '隔离进程无法回传失败结果'
            )


def _assign_windows_memory_limit(process, memory_limit_mb):
    if os.name != 'nt' or not memory_limit_mb:
        return None
    try:
        import win32api
        import win32con
        import win32job

        job = win32job.CreateJobObject(None, '')
        info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        info['BasicLimitInformation']['LimitFlags'] |= (
            win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info['ProcessMemoryLimit'] = int(memory_limit_mb) * 1024 * 1024
        win32job.SetInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation, info
        )
        process_handle = win32api.OpenProcess(
            win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE,
            False,
            process.pid,
        )
        try:
            win32job.AssignProcessToJobObject(job, process_handle)
        finally:
            win32api.CloseHandle(process_handle)
        return job
    except Exception as exc:
        raise RuntimeError(
            '无法为隔离进程启用 Windows 内存上限'
        ) from exc


def run_isolated_worker(
    worker,
    args,
    *,
    timeout: int,
    label: str,
    memory_limit_mb: int | None = None,
):
    if isinstance(timeout, bool) or int(timeout) <= 0:
        raise ValueError('隔离进程超时时间必须为正整数')
    if (
        memory_limit_mb is not None
        and (isinstance(memory_limit_mb, bool) or int(memory_limit_mb) <= 0)
    ):
        raise ValueError('隔离进程内存上限必须为正整数')
    context = multiprocessing.get_context('spawn')
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_worker_entry,
        args=(worker, args, result_queue, memory_limit_mb),
        daemon=True,
    )
    job_handle = None
    try:
        process.start()
        try:
            job_handle = _assign_windows_memory_limit(process, memory_limit_mb)
        except Exception:
            process.terminate()
            process.join(5)
            raise
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.terminate()
                process.join(5)
                if process.is_alive() and hasattr(process, 'kill'):
                    process.kill()
                    process.join(5)
                raise RuntimeError(f'{label}超时（{timeout} 秒），转换进程已终止')
            try:
                status, payload = result_queue.get(timeout=min(0.25, remaining))
                break
            except queue.Empty as exc:
                if not process.is_alive():
                    raise RuntimeError(
                        f'{label}进程异常退出（代码 {process.exitcode}）'
                    ) from exc
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
        if status == 'value_error':
            raise ValueError(str(payload))
        if status != 'ok':
            raise RuntimeError(str(payload or f'{label}失败'))
        return payload
    finally:
        if job_handle is not None:
            try:
                import win32api

                win32api.CloseHandle(job_handle)
            except (ImportError, OSError):
                logging.getLogger('contract_tool').warning(
                    '关闭隔离进程内存限制句柄失败',
                    exc_info=True,
                )
        result_queue.close()
        result_queue.join_thread()
