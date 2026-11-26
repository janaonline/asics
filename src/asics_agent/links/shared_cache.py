"""The shared copy cache: a page opened once is not fetched (or paid for) again by another city or step.

Layout, under `<outputs root>/_cache/` (git-ignored, outside every city's folder):

    fetch/<key>/meta.json        what is cached for one address: the newest copy and when it was made
    fetch/<key>/<hash>.txt       the readable text of each version (the key is `norm_key(url)` hashed)
    fetch/<key>/<hash>.<ext>     the page or PDF as downloaded, when it is small enough to keep
    fetch/<key>/original.pdf     the bytes of a PDF that could not be read (scan or damaged), so a later
                                 run with a bigger scan budget does not download it again
    scans/<sha1 of the PDF>/     scan_reading.py's work on one document (chunks, batch, cost)

A hit copies the text and the snapshot into the city's own `evidence/` folder under the usual name, so
`Source.content_path`, Steps 2 and 3 and `links.db` work exactly as before; the copy's mark comes with it.
A live copy is reused for `fetch_cache_max_age_days` (default 30); an archived copy expires the same way,
so a site that recovers is fetched again; a scan-read copy never expires (the PDF would have to change).
Only a copy that passed the content checks is stored. A team's hand-saved copy never goes through here.
"""

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from asics_agent.links import marks
from asics_agent.models import AccessCheck

SNAPSHOT_LIMIT_BYTES = (
    30 * 1024 * 1024
)  # larger downloads are not copied into a city's evidence folder
_lock = threading.RLock()


def _norm_key(url: str) -> str:
    from asics_agent.links.fetch_chain import norm_key  # the one definition of "the same page"

    return norm_key(url)


def folder_for(root: Path, url: str) -> Path:
    return root / "fetch" / hashlib.sha1(_norm_key(url).encode()).hexdigest()[:16]


def _stem(url: str) -> str:
    """The name a city's evidence files carry (accessibility.accept_text writes the same)."""
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


class SharedCache:
    def __init__(self, root: Path | None, max_age_days: int = 30, today=None):
        self.root = root
        self.max_age_days = max_age_days
        self._now = today or (lambda: datetime.now(UTC))

    # -- copies ------------------------------------------------------------------------------------
    def lookup(self, url: str, evidence_dir: Path) -> AccessCheck | None:
        """The cached copy of `url`, copied into `evidence_dir`, or None (no copy, too old, or off)."""
        if self.root is None or self.max_age_days <= 0:
            return None
        folder = folder_for(self.root, url)
        with _lock:
            meta = _read(folder / "meta.json")
            text_file = folder / f"{meta.get('hash', '')}.txt"
            if not meta or not text_file.exists():
                return None
            if not self._fresh(meta):
                return None
            evidence_dir.mkdir(parents=True, exist_ok=True)
            stem = _stem(url)
            text_path = evidence_dir / f"{stem}.txt"
            text_path.write_text(text_file.read_text(encoding="utf-8"), encoding="utf-8")
            snapshot = None
            kept = folder / f"{meta['hash']}{meta.get('snapshot_ext', '')}"
            if meta.get("snapshot_ext") and kept.exists():
                snapshot = evidence_dir / f"{stem}{meta['snapshot_ext']}"
                snapshot.write_bytes(kept.read_bytes())
        check = AccessCheck(url=url, checked_at=self._now().isoformat(timespec="seconds"))
        check.verification_status = "Verified"
        check.accessibility = "Public"
        check.status_code = 200
        check.words = int(meta.get("words") or 0)
        check.content_path = str(text_path)
        check.snapshot_path = str(snapshot) if snapshot else None
        check.final_url = meta.get("final_url") or None
        check.copy_type = meta.get("copy_type", "")
        check.archived_on = meta.get("archived_on", "")
        check.stages = [f"shared cache (copy made {meta.get('fetched_at', '?')[:10]})"]
        check.reasons.append(
            f"Copy reused from the shared cache (made {meta.get('fetched_at', '?')[:10]}): no new "
            f"download. {check.words} words of readable content."
        )
        check.reasons += list(meta.get("reasons") or [])
        if check.copy_type and not meta.get("reasons"):
            check.reasons.append(f"Copy type: {check.copy_type}.")
        return check

    def _fresh(self, meta: dict) -> bool:
        if meta.get("never_expires"):
            return True
        try:
            made = datetime.fromisoformat(meta["fetched_at"])
        except (KeyError, ValueError):
            return False
        return self._now() - made < timedelta(days=self.max_age_days)

    def store(
        self, url: str, check: AccessCheck, *, never_expires: bool = False, extra=None
    ) -> bool:
        """Keep the copy `check` produced (its saved text and snapshot). False when there is nothing to
        keep (no text on disk, not Verified, a hand-saved team copy)."""
        if self.root is None or check.verification_status != "Verified" or not check.content_path:
            return False
        if marks.has(check.copy_type, marks.SAVED_BY_TEAM) or marks.has(
            check.copy_type, marks.SCAN_PENDING
        ):
            return False
        source = Path(check.content_path)
        if not source.exists():
            return False
        text = source.read_text(encoding="utf-8")
        digest = hashlib.sha1(text.encode()).hexdigest()[:12]
        folder = folder_for(self.root, url)
        ext = Path(check.snapshot_path).suffix if check.snapshot_path else ""
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{digest}.txt").write_text(text, encoding="utf-8")
            kept_ext = ""
            if ext and Path(check.snapshot_path).exists():
                data = Path(check.snapshot_path).read_bytes()
                if len(data) <= SNAPSHOT_LIMIT_BYTES:
                    (folder / f"{digest}{ext}").write_bytes(data)
                    kept_ext = ext
            meta = {
                "url": url,
                "final_url": check.final_url or "",
                "hash": digest,
                "words": check.words,
                "copy_type": check.copy_type,
                "archived_on": check.archived_on,
                "fetched_at": self._now().isoformat(timespec="seconds"),
                "snapshot_ext": kept_ext,
                "never_expires": bool(never_expires),
                **(extra or {}),
            }
            (folder / "meta.json").write_text(json.dumps(meta, indent=1))
            # the older version stays (its hash differs); meta.json names the newer one
        return True

    # -- a PDF that could not be read ----------------------------------------------------------------
    def save_original(self, url: str, data: bytes) -> Path | None:
        if self.root is None:
            return None
        folder = folder_for(self.root, url)
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "original.pdf"
            if not path.exists() or path.stat().st_size != len(data):
                path.write_bytes(data)
            meta = _read(folder / "original.json")
            meta.update(
                {
                    "url": url,
                    "bytes": len(data),
                    "saved_at": self._now().isoformat(timespec="seconds"),
                }
            )
            (folder / "original.json").write_text(json.dumps(meta, indent=1))
        return path

    def original_fresh(self, url: str) -> bytes | None:
        """The saved bytes of an unreadable PDF, when they were saved within `max_age_days`."""
        path = self.original(url)
        if path is None or self.max_age_days <= 0:
            return None
        try:
            saved = datetime.fromisoformat(
                _read(path.with_name("original.json")).get("saved_at", "")
            )
        except ValueError:
            return None
        if self._now() - saved >= timedelta(days=self.max_age_days):
            return None
        return path.read_bytes()

    def original(self, url: str) -> Path | None:
        if self.root is None:
            return None
        path = folder_for(self.root, url) / "original.pdf"
        return path if path.exists() else None
