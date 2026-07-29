"""Run picklable callables in killable subprocesses with hard timeouts."""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any


class SubprocessTimeoutError(TimeoutError):
    """Raised when a subprocess exceeds its configured deadline."""


class SubprocessExecutionError(RuntimeError):
    """Raised when a subprocess callable fails."""


def _worker(
    send_conn: Connection,
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    try:
        send_conn.send(("ok", func(*args, **kwargs)))
    except BaseException as exc:
        send_conn.send(("error", type(exc).__name__, str(exc)))
    finally:
        send_conn.close()


def run_in_subprocess(
    func: Callable[..., Any],
    *args: Any,
    timeout_seconds: float,
    **kwargs: Any,
) -> Any:
    """Run ``func`` in a spawned process and terminate it on timeout."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    context = multiprocessing.get_context("spawn")
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker,
        args=(send_conn, func, args, kwargs),
    )
    process.start()
    send_conn.close()

    try:
        if not recv_conn.poll(timeout_seconds):
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join()
            raise SubprocessTimeoutError(
                f"subprocess exceeded {timeout_seconds:g}s deadline"
            )

        message = recv_conn.recv()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join()

        if message[0] == "error":
            _, error_type, detail = message
            raise SubprocessExecutionError(f"{error_type}: {detail}")
        return message[1]
    finally:
        recv_conn.close()
        if process.is_alive():
            process.terminate()
        process.join()
        process.close()
