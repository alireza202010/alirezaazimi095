"""Thin HTTP wrapper: retries with backoff and a polite delay between calls."""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = "HashinGold-LeadAgent/1.0 (sales lead research)"


class Http:
    def __init__(self, delay: float = 0.2, retries: int = 3, timeout: float = 60.0):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.calls = 0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(self.retries + 1):
            if self.delay:
                time.sleep(self.delay)
            self.calls += 1
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                if attempt == self.retries:
                    raise
                log.warning("%s %s failed (%s), retrying", method, url, exc)
            else:
                if resp.status_code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    resp.raise_for_status()
                    return resp
                log.warning("%s %s -> HTTP %s, retrying", method, url, resp.status_code)
            time.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post_json(self, url: str, payload: dict, **kwargs) -> requests.Response:
        return self.request("POST", url, json=payload, **kwargs)

    def post_form(self, url: str, data: dict, **kwargs) -> requests.Response:
        return self.request("POST", url, data=data, **kwargs)
