import time

import pytest

from applypilot.subprocess_runner import (
    SubprocessExecutionError,
    SubprocessTimeoutError,
    run_in_subprocess,
)


def _add(left: int, right: int) -> int:
    return left + right


def _fail() -> None:
    raise LookupError("broken source")


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def test_run_in_subprocess_returns_result() -> None:
    assert run_in_subprocess(_add, 2, 3, timeout_seconds=2) == 5


def test_run_in_subprocess_propagates_error() -> None:
    with pytest.raises(SubprocessExecutionError, match="LookupError: broken source"):
        run_in_subprocess(_fail, timeout_seconds=2)


def test_run_in_subprocess_terminates_at_deadline() -> None:
    started = time.monotonic()

    with pytest.raises(SubprocessTimeoutError):
        run_in_subprocess(_sleep, 5, timeout_seconds=0.1)

    assert time.monotonic() - started < 2
