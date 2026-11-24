"""What would scan reading read, and cost, in the cities already run? Free: no model call.

Reads the latest Sources workbook of each city (read only: nothing is written to it or to outputs/), picks
the rows the link check left as a scanned PDF or an unreadable PDF, finds each document's page count, and
lays them against the scan budget in the order the real pass uses: legal texts ([ACT], [RULES]) and the
documents the questions require first, then the rest, smallest first inside each group.

A document's pages are counted from the saved copy in the city's evidence folder when there is one; the
others are downloaded ONCE into a scratch folder (a plain, certificate-verified GET; a site whose certificate cannot be checked is reported as not downloaded): by the time the link check
failed, their bytes were not kept. Costs use the scan reader's own figures (live $0.013 a page, batch half).

    uv run python scripts/scan_estimate.py                       # Bengaluru and Bhubaneswar
    uv run python scripts/scan_estimate.py Surat --scratch /tmp/pdfs
"""

import argparse
import hashlib
import io
import warnings
from pathlib import Path

import httpx
from pypdf import PdfReader

from asics_agent.agents.scan_step import priority
from asics_agent.categories import category_settings
from asics_agent.config import PROJECT_ROOT, get_settings
from asics_agent.links import pdf_tools
from asics_agent.links.accessibility import MAX_PDF_BYTES, make_http_client
from asics_agent.links.scan_reading import BATCH_FACTOR, BATCH_MIN_CHUNKS, PER_PAGE_USD
from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for

warnings.filterwarnings("ignore")

# Measured in the one real call (5 pages of a Kannada memo): $0.030 a page live, 2.3 times the English figure
KANNADA_PER_PAGE_USD = 0.030
DEFAULT_CITIES = ("Bengaluru", "Bhubaneswar")


def picks(source) -> str:
    """Why the link check left this row for scan reading ("" = not a candidate), from its Notes."""
    notes = source.notes or ""
    if "probably a scan" in notes:
        return "scan, no text layer"
    if "could not be read (Pdf" in notes:
        return "unreadable (PdfReadError/PdfStreamError)"
    if "Larger than the download limit" in notes:
        return "over the download limit"
    return ""


def fetch(source, evidence: Path, scratch: Path, client: httpx.Client) -> tuple[bytes | None, str]:
    stem = hashlib.sha1(source.url.encode()).hexdigest()[:16]
    for place, name in ((evidence, f"{stem}.pdf"), (scratch, f"{stem}.pdf")):
        path = place / name
        if path.exists() and path.stat().st_size and path.read_bytes()[:5] == b"%PDF-":
            data = path.read_bytes()
            if len(data) < MAX_PDF_BYTES:
                return data, "saved copy" if place == evidence else "downloaded earlier"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        response = client.get(source.url, follow_redirects=True, timeout=180)
        how = "downloaded"
    except httpx.HTTPError as exc:
        return None, f"could not download ({type(exc).__name__})"
    if response.status_code != 200 or response.content[:5] != b"%PDF-":
        return None, f"could not download (HTTP {response.status_code})"
    (scratch / f"{stem}.pdf").write_bytes(response.content)
    return response.content, how


def inspect(data: bytes) -> dict:
    """pages, words of extractable text, and what the app would do with the file."""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        words = [len((p.extract_text() or "").split()) for p in reader.pages]
        empty = sum(w < 10 for w in words)
        if empty / pages < 0.5:
            return {
                "pages": pages,
                "words": sum(words),
                "verdict": "readable text: no Claude needed",
            }
        return {
            "pages": pages,
            "words": sum(words),
            "verdict": "scan: Claude reads the PDF",
            "kind": "pdf",
        }
    except Exception as exc:
        fixed = pdf_tools.repair(data)
        pages = pdf_tools.page_count(fixed) if fixed else None
        if pages is None:
            return {"pages": None, "words": 0, "verdict": f"unopenable ({type(exc).__name__})"}
        return {
            "pages": pages,
            "words": 0,
            "verdict": "repaired, then read as page images",
            "kind": "images",
        }


def cost(pages: int) -> tuple[float, float]:
    live = pages * PER_PAGE_USD
    n_chunks = len(pdf_tools.chunk_ranges(pages))
    return live, live * (BATCH_FACTOR if n_chunks >= BATCH_MIN_CHUNKS else 1)


def spend(items: list[dict], budget: float) -> tuple[list[dict], float]:
    """The real pass: value first, smallest first inside a group; a document that does not fit is skipped
    whole. Marks each item "read" or "over budget"; returns the items in reading order and the spend."""
    used = 0.0
    ordered = sorted(items, key=lambda i: (i["priority"], i["pages"]))
    for item in ordered:
        if used + item["est"] <= budget + 1e-9:
            used += item["est"]
            item["outcome"] = "read"
        else:
            item["outcome"] = "OVER BUDGET: not read"
    return ordered, used


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cities", nargs="*", default=list(DEFAULT_CITIES))
    ap.add_argument("--scratch", type=Path, default=PROJECT_ROOT / "scratch" / "stage1b" / "pdfs")
    ap.add_argument(
        "--out", type=Path, default=PROJECT_ROOT / "scratch" / "stage1b" / "scan_estimate.md"
    )
    args = ap.parse_args(argv)
    settings = category_settings(get_settings(), "parastatal")
    budget = settings.scan_reading_budget_usd
    client = make_http_client(settings.user_agent, 60)
    lines = [
        f"# Scan reading: what the latest workbooks would send to Claude (budget ${budget:,.2f} a run)\n"
    ]
    everything: list[dict] = []
    for city in args.cities:
        workspace = workspace_for(settings.outputs_dir, city)
        path = sources_path(workspace, city)
        if not path.exists():
            lines.append(f"\n## {city}\nNo Sources workbook.\n")
            continue
        _, sources, _ = read_sources_workbook(path, workspace / "evidence")
        items = []
        for s in sources:
            if not (why := picks(s)):
                continue
            data, how = fetch(s, workspace / "evidence", args.scratch, client)
            info = inspect(data) if data else {"pages": None, "verdict": how}
            item = {
                "city": city,
                "agency": s.parastatal_id,
                "title": s.title[:60],
                "url": s.url,
                "why": why,
                "how": how,
                "priority": priority(s),
                "tags": s.useful_for.split("]")[0].lstrip("[") if "[" in s.useful_for else "",
                **info,
            }
            if info.get("kind") and info["pages"]:
                item["est"] = cost(info["pages"])[1]
                item["live"] = cost(info["pages"])[0]
            items.append(item)
        everything += items
        lines += table(city, items, budget)
    both = [dict(i) for i in everything]
    if len(args.cities) > 1:
        lines += table("All cities in ONE run", both, budget)
    text = "\n".join(lines)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(text)
    print(f"\nwritten to {args.out}")
    return 0


def table(title: str, items: list[dict], budget: float) -> list[str]:
    readable = [i for i in items if i.get("kind") and i.get("pages")]
    ordered, used = spend(readable, budget)
    pages = sum(i["pages"] for i in readable)
    live = sum(i["live"] for i in readable)
    batch = sum(i["est"] for i in readable)
    dear = batch * KANNADA_PER_PAGE_USD / PER_PAGE_USD
    out = [
        f"\n## {title}\n",
        f"| Agency | Document | Group | Why it was left | What it is | Pages | Live $ | Batch/live $ used | Order | In a ${budget:,.2f} run |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    order = {id(i): n for n, i in enumerate(ordered, 1)}
    for i in sorted(items, key=lambda i: (i["agency"], i["title"])):
        if i.get("kind") and i.get("pages"):
            nums = (f"{i['live']:.2f}", f"{i['est']:.2f}", str(order[id(i)]), i["outcome"])
        else:
            nums = ("-", "-", "-", "nothing to read" if i.get("pages") else "not checked")
        out.append(
            f"| {i['agency']} | {i['title']} ({i['url'][-40:]}) | "
            f"{('legal', 'required', 'other')[i['priority']]} | {i['why']} | {i['verdict']} | "
            f"{i.get('pages') or '?'} | {nums[0]} | {nums[1]} | {nums[2]} | {nums[3]} |"
        )
    out.append(
        f"\nTo read: {len(readable)} document(s), {pages} pages. All of it: **${live:,.2f} live, "
        f"${batch:,.2f} as batches (documents of 4+ chunks)** at the English-script price; "
        f"${dear:,.2f} as batches if every page costs what the Kannada test did. Within ${budget:,.2f}: **${used:,.2f}** "
        f"spent, {sum(i['outcome'] == 'read' for i in readable)} of {len(readable)} read.\n"
    )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
