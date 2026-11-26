"""The archive stage of the fetch chain: the Internet Archive's Wayback Machine.

Asks archive.org for the snapshot closest to now and downloads its raw copy (the `id_` form, without
the archive's own banner). Polite: one request at a time in the whole process, at least `min_gap`
seconds apart, and a slow retry when the archive answers 429.
"""

import threading
import time
from dataclasses import dataclass
from datetime import date

import httpx

AVAILABLE = "https://archive.org/wayback/available"
RAW = "https://web.archive.org/web/{stamp}id_/{url}"
_gate = threading.Lock()
_last = [0.0]


@dataclass
class WaybackResult:
    ok: bool
    body: bytes = b""
    content_type: str = ""
    archived_on: str = ""  # ISO date of the snapshot
    snapshot_url: str = ""
    error: str = ""  # "no archived copy", "HTTP 429 ...", ...


class Wayback:
    def __init__(
        self, client: httpx.Client | None = None, *, min_gap: float = 10.0, sleep=time.sleep
    ):
        self._client = client
        self.min_gap, self._sleep = min_gap, sleep

    def _http(self) -> httpx.Client:
        if self._client is None:
            from asics_agent.links.accessibility import make_http_client

            self._client = make_http_client("", 40)
        return self._client

    def _get(self, url: str, **kw) -> httpx.Response:
        """One request, spaced from the last, retried slowly on 429."""
        for attempt in range(3):
            with _gate:
                wait = self.min_gap - (time.monotonic() - _last[0])
                if wait > 0:
                    self._sleep(wait)
                try:
                    response = self._http().get(url, follow_redirects=True, **kw)
                finally:
                    _last[0] = time.monotonic()
            if response.status_code != 429 or attempt == 2:
                return response
            self._sleep(20)
        return response  # pragma: no cover

    def fetch(self, url: str) -> WaybackResult:
        try:
            meta = self._get(AVAILABLE, params={"url": url})
            if meta.status_code != 200:
                return WaybackResult(False, error=f"HTTP {meta.status_code} from the archive")
            snap = (meta.json().get("archived_snapshots") or {}).get("closest") or {}
            if not snap.get("available"):
                return WaybackResult(False, error="no archived copy")
            stamp = str(snap["timestamp"])
            day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
            raw = RAW.format(stamp=stamp, url=url)
            copy = self._get(raw)
            if copy.status_code != 200:
                return WaybackResult(
                    False,
                    archived_on=day,
                    snapshot_url=raw,
                    error=f"HTTP {copy.status_code} on the copy",
                )
            ctype = copy.headers.get("content-type", "").split(";")[0].strip().lower()
            return WaybackResult(True, copy.content, ctype, day, raw)
        except (httpx.HTTPError, ValueError) as exc:
            return WaybackResult(False, error=f"{type(exc).__name__}")


def age_days(archived_on: str, today: date | None = None) -> int | None:
    try:
        return ((today or date.today()) - date.fromisoformat(archived_on)).days
    except ValueError:
        return None
