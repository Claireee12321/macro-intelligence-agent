"""HTTP helpers: shared session, timeouts, retry with backoff.

The ``retry`` helper is adapted from MarketBrief's ``utils/retry.py`` (MIT); unlike the
original it re-raises after the last attempt instead of silently returning ``{}``, so
callers can record a real failure for the source, and it never retries permanent errors.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, TypeVar

import requests

log = logging.getLogger("macro_intel")
T = TypeVar("T")

DEFAULT_UA = "MacroIntelligenceAgent/0.2 (personal research)"
_local = threading.local()


class PermanentHTTPError(requests.HTTPError):
    """4xx (other than 429): retrying will not help."""


def session() -> requests.Session:
    """A per-thread requests session (requests.Session is not thread-safe)."""
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": DEFAULT_UA, "Accept": "*/*"})
        _local.session = s
    return s


def retry(fn: Callable[[], T], attempts: int = 3, delay: float = 1.5, label: str = "") -> T:
    """Call ``fn`` until it succeeds; exponential backoff; re-raise the last error."""
    tag = label or getattr(fn, "__name__", "call")
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except PermanentHTTPError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised after the last attempt
            last = exc
            if attempt < attempts:
                wait = delay * (2 ** (attempt - 1))
                log.warning("%s: attempt %d/%d failed (%s); retrying in %.1fs", tag, attempt, attempts, exc, wait)
                time.sleep(wait)
    assert last is not None
    raise last


def get(
    url: str,
    *,
    timeout: float = 20.0,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 3,
    label: str = "",
) -> requests.Response:
    """GET with retry on network errors, 429 and 5xx; raises immediately on other 4xx."""

    def _do() -> requests.Response:
        resp = session().get(url, params=params, headers=headers, timeout=timeout)
        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            raise PermanentHTTPError(f"HTTP {resp.status_code} for {label or url}", response=resp)
        resp.raise_for_status()
        return resp

    return retry(_do, attempts=attempts, label=label or url)
