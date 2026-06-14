from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from urllib.parse import urlparse

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_exponential_jitter

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_BYTES = 1_500_000
MIN_HOST_INTERVAL = 0.15

_rate_lock = threading.Lock()
_host_locks: dict[str, threading.Lock] = {}
_last_request_by_host: dict[str, float] = {}


@dataclass(slots=True)
class FetchedPage:
    body: str
    raw_bytes: bytes
    final_url: str
    status_code: int
    content_type: str
    charset: str
    bytes_read: int
    truncated: bool


class FetchFailure(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: str,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable


def _wait_for_host(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return
    with _rate_lock:
        host_lock = _host_locks.setdefault(host, threading.Lock())
    with host_lock:
        now = time.monotonic()
        wait_for = MIN_HOST_INTERVAL - (now - _last_request_by_host.get(host, 0))
        if wait_for > 0:
            time.sleep(wait_for)
        _last_request_by_host[host] = time.monotonic()


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, FetchFailure) and exc.retryable


def _fetch_once(
    url: str,
    *,
    user_agent: str,
    timeout: float,
    max_bytes: int,
    accept: str,
) -> FetchedPage:
    _wait_for_host(url)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": user_agent,
                "Accept": accept,
            },
        ) as client:
            with client.stream("GET", url) as response:
                status = response.status_code
                if status in {401, 403}:
                    raise FetchFailure(
                        f"HTTP {status}",
                        kind="blocked",
                        status_code=status,
                    )
                if status == 429:
                    raise FetchFailure(
                        "HTTP 429",
                        kind="rate-limited",
                        status_code=status,
                        retryable=True,
                    )
                if 500 <= status <= 599:
                    raise FetchFailure(
                        f"HTTP {status}",
                        kind="server",
                        status_code=status,
                        retryable=True,
                    )
                if status >= 400:
                    raise FetchFailure(
                        f"HTTP {status}",
                        kind="http",
                        status_code=status,
                    )

                chunks = bytearray()
                truncated = False
                for chunk in response.iter_bytes():
                    remaining = max_bytes - len(chunks)
                    if remaining <= 0:
                        truncated = True
                        break
                    chunks.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated = True
                        break
                charset = response.encoding or "utf-8"
                return FetchedPage(
                    body=bytes(chunks).decode(charset, errors="replace"),
                    raw_bytes=bytes(chunks),
                    final_url=str(response.url),
                    status_code=status,
                    content_type=response.headers.get("content-type", ""),
                    charset=charset,
                    bytes_read=len(chunks),
                    truncated=truncated,
                )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise FetchFailure(
            str(exc),
            kind="network",
            retryable=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise FetchFailure(str(exc), kind="client") from exc

def fetch_page(
    url: str,
    *,
    user_agent: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    attempts: int = 3,
    accept: str = "text/html,application/xhtml+xml",
) -> FetchedPage:
    retrying = Retrying(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=0.5, max=8),
        reraise=True,
    )
    return retrying(
        _fetch_once,
        url,
        user_agent=user_agent,
        timeout=timeout,
        max_bytes=max_bytes,
        accept=accept,
    )
