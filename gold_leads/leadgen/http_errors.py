"""Helpers for reading HTTP failures raised by ``Http`` (requests) or test doubles."""

from __future__ import annotations


def status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def is_auth_error(exc: BaseException) -> bool:
    return status_of(exc) in (401, 403)
