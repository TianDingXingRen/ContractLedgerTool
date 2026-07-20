"""Run unsafe desktop automation in a hard-time-limited child process."""

from __future__ import annotations

import multiprocessing
import queue


def run_isolated_worker(worker, args, *, timeout: int, label: str):
    context = multiprocessing.get_context('spawn')
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=worker, args=(*args, result_queue), daemon=True)
    process.start()
    try:
        process.join(timeout)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive() and hasattr(process, 'kill'):
                process.kill()
                process.join(5)
            raise RuntimeError(f'{label}超时（{timeout} 秒），转换进程已终止')
        try:
            status, payload = result_queue.get(timeout=1)
        except queue.Empty as exc:
            raise RuntimeError(f'{label}进程异常退出（代码 {process.exitcode}）') from exc
        if status != 'ok':
            raise RuntimeError(str(payload or f'{label}失败'))
        return payload
    finally:
        result_queue.close()
        result_queue.join_thread()
