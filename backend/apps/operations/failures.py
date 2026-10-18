"""Explicit Paper failure injection; inaccessible to HTTP and disabled by default."""

from contextlib import contextmanager
from contextvars import ContextVar

_fault = ContextVar("paper_failure_point", default=None)


@contextmanager
def inject_paper_failure(point):
    if point not in {"before_submit", "after_submit"}:
        raise ValueError("Unsupported Paper failure point.")
    token = _fault.set(point)
    try:
        yield
    finally:
        _fault.reset(token)


def fail_once(point):
    if _fault.get() != point:
        return
    _fault.set(None)
    raise TimeoutError(f"injected_{point}")
