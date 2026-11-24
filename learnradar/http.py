from __future__ import annotations

import threading
import time

import requests

USER_AGENT = "learning-radar/0.1 (+https://github.com/girimohan/learning-radar)"
_local = threading.local()


def session() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers["User-Agent"] = USER_AGENT
        _local.s.headers["Accept"] = "application/json, */*;q=0.5"
    return _local.s


class FetchError(Exception):
    pass


def get(url: str, *, params: dict | None = None, tries: int = 3, timeout=(8, 90), json_body: dict | None = None):
    """GET (or POST when json_body is given) with polite retries. Returns parsed JSON, None for 404/410.

    Raises FetchError for anything else that is not a success.
    """
    last = "no attempt"
    for attempt in range(tries):
        try:
            if json_body is not None:
                r = session().post(url, params=params, json=json_body, timeout=timeout)
            else:
                r = session().get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            last = type(e).__name__
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (404, 410):
            return None
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            time.sleep(float(r.headers.get("retry-after") or 5 * (attempt + 1)))
            continue
        if not r.ok:
            raise FetchError(f"HTTP {r.status_code} for {url}")
        try:
            return r.json()
        except ValueError as e:
            raise FetchError(f"bad JSON from {url}") from e
    raise FetchError(f"{last} for {url}")
