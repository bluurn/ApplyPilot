"""Global cancellation signal for pipeline runs."""

import threading

_event = threading.Event()


def request() -> None:
    _event.set()


def clear() -> None:
    _event.clear()


def is_set() -> bool:
    return _event.is_set()
