"""How a saved copy was obtained: the marks that go in the Citation Sheet's "Copy Type" column.

A mark says which stage of the fetch chain (fetch_chain.py) produced the text, so a reviewer knows what
they are looking at. Marks combine with "; " ("browser-rendered; certificate not verified"). Plain
code, no network: the gate (source_requirements.py) and the Needs Attention lines read it too.
"""

PLAIN = "plain HTTP"
BROWSER = "browser-rendered"
CERT = "certificate not verified"
SCAN = "read by Claude (scan)"
PARTIAL_SCAN = "partial scan"
SAVED_BY_TEAM = "saved by team"
STALE = "stale archive"
_ARCHIVED = "ARCHIVED"


def archived(day: str) -> str:
    """ "ARCHIVED 2024-03-02" for a Wayback snapshot taken that day."""
    return f"{_ARCHIVED} {day}".strip()


def join(*parts: str) -> str:
    return "; ".join(p for p in parts if p)


def has(copy_type: str, mark: str) -> bool:
    return mark.lower() in (copy_type or "").lower()


def is_archived(copy_type: str) -> bool:
    """An archived copy (stale or not): usable for a positive finding, never the basis for a zero."""
    return has(copy_type, _ARCHIVED)


def is_stale(copy_type: str) -> bool:
    return has(copy_type, STALE)


def cannot_support_zero(copy_type: str) -> bool:
    """A copy that may support a positive finding but must not be the basis for a zero, and does not
    satisfy a required-source or complete-crawl check: an archived copy (and a partial scan)."""
    return is_archived(copy_type) or has(copy_type, PARTIAL_SCAN)
