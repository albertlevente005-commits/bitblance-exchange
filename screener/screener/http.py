"""Közös HTTP-réteg: rate limit, újrapróbálás, tesztelhető transport."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

# transport(url, params, headers) -> (status_code, json_body | None, headers)
Transport = Callable[[str, dict | None, dict | None], tuple[int, Any, dict]]


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: Any = None):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url
        self.body = body


def _requests_transport(timeout: float) -> Transport:
    session = requests.Session()
    session.headers["User-Agent"] = "crypto-screener/0.1 (+https://github.com)"

    def transport(url: str, params: dict | None, headers: dict | None):
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
        try:
            body = resp.json()
        except ValueError:
            body = None
        return resp.status_code, body, dict(resp.headers)

    return transport


class Http:
    """Egy adatforráshoz tartozó kliens: saját sebességkorláttal és újrapróbálással."""

    def __init__(
        self,
        name: str,
        min_interval: float = 0.0,
        timeout: float = 30.0,
        retries: int = 3,
        headers: dict | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.name = name
        self.min_interval = min_interval
        self.retries = retries
        self.headers = headers or {}
        self.transport = transport or _requests_transport(timeout)
        self.sleep = sleep
        self._last = 0.0
        self.calls = 0

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            self.sleep(wait)
        self._last = time.monotonic()

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any:
        merged = {**self.headers, **(headers or {})}
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle()
            self.calls += 1
            try:
                status, body, resp_headers = self.transport(url, params, merged)
            except requests.RequestException as exc:  # hálózati hiba
                last_err = exc
                log.warning("%s: hálózati hiba (%s), próba %d", self.name, exc, attempt + 1)
                self.sleep(2 ** attempt)
                continue
            if status == 200:
                return body
            if status in (429, 500, 502, 503, 504) and attempt < self.retries:
                retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else 2.0 * (2 ** attempt)
                except ValueError:
                    delay = 2.0 * (2 ** attempt)
                log.warning("%s: HTTP %s, várakozás %.1fs (%s)", self.name, status, delay, url)
                self.sleep(min(delay, 120))
                continue
            raise HttpError(status, url, body)
        raise HttpError(0, url, str(last_err))

    def try_get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> Any | None:
        """Mint get_json, de hiba esetén None (best-effort források)."""
        try:
            return self.get_json(url, params, headers)
        except (HttpError, requests.RequestException) as exc:
            log.warning("%s: kihagyva %s (%s)", self.name, url, exc)
            return None
