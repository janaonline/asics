"""Which sources a question needs before a score of 0 is allowed (Parastatal category).

The programme team's rule: the methodology's zero condition ("0 if no such provision exists", "0 if
no official website is found") may be used only when the agency's Citation Sheet holds every source
the question requires and those sources were read. This module holds the pieces, all plain code with
no model call:

  load / required_for   the table in data/question_source_requirements.yaml (one row per question)
  tags_of               the evidence tags of a Citation Sheet row ([ACT], [RULES], [TCP] ...)
  legal_base_kind       whether the agency's legal basis is a parent Act or a constitution document
  check                 are all required sources present, missing, or present but failed to open?
  scan_required         a scan of the full text of every required document for relevant passages
  decide_zero           check and scan together: may a zero be given, and the note to write

The table is a draft built by the project team's tooling; nothing in it has been reviewed by a person.
When unsure a row requires more, so a wrong row keeps today's blank rather than allowing a false 0.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from asics_agent import cutoff
from asics_agent.config import PROJECT_ROOT
from asics_agent.links.accessibility import site_of
from asics_agent.models import Parastatal, Source

TABLE_PATH = PROJECT_ROOT / "data" / "question_source_requirements.yaml"
ZERO_CHECKED = "ZERO-CHECKED"  # marker written in a Step 2 note for a zero given by the gate
# Written in the Notes of the agency's home page row by Step 1's site crawl:
# "SITE-CRAWL: complete, 12 of 12 links." or "SITE-CRAWL: incomplete, ..."
SITE_CRAWL = "SITE-CRAWL"

_TAG = re.compile(r"\[([A-Za-z][A-Za-z0-9\-]*)\]")
# Other spellings the finder has used for the agency's own website
_SYNONYMS = {"AGENCY-WEBSITE": "WEB", "PARASTATAL-OFFICIAL-SITE": "WEB"}
# A row on the agency's own site carrying one of these tags is a page of that site. The crawl tags
# its pages [WEB]. A website question counts such pages only when the crawl is complete (see check).
WEBPAGE_TAGS = frozenset(
    "WEB WEB-FEATURE RTI GRIEV PROCURE CHARTER BUDGET AR ACCOUNTS MINUTES PLANS SECTORPLAN SLB TARIFF "
    "STAFF-DATA ORG BOARD-LIST FISCALPLAN PARTICIPATION CE-APPT".split()
)
# What the team reads in "Missing: <document>"
DOCUMENT_NAMES = {
    "ACT": "parent Act [ACT]",
    "CONSTITUTION": "constitution document (MoA/AoA, incorporation order or board resolution) "
    "[CONSTITUTION]",
    "RULES": "Rules made under the Act [RULES]",
    "TCP": "Town and Country Planning Act [TCP]",
    "ULG-LAW": "State Municipal Act [ULG-LAW]",
    "BUDGET": "annual budget [BUDGET]",
    "ACCOUNTS": "annual accounts / financial statements [ACCOUNTS]",
    "AR": "annual report [AR]",
    "PLANS": "plan document [PLANS or SECTORPLAN]",
    "SECTORPLAN": "plan document [PLANS or SECTORPLAN]",
    "TARIFF": "tariff or fare orders [TARIFF]",
    "CE-APPT": "chief executive appointment records [CE-APPT]",
    "BOARD-LIST": "current board list [BOARD-LIST]",
    "WEB": "official website [WEB]",
    "WEBPAGE": "pages of the agency's own website reached from the home page menu",
    "SITECRAWL": "complete site crawl (every menu link on the home page captured)",
    "MINUTES": "board minutes [MINUTES]",
}
# General laws that create companies and societies: not a "parent Act" of the agency
_GENERAL_LAWS = re.compile(
    r"companies act|societies registration act|registration act|trusts? act|co-?operative societies",
    re.I,
)
_NO_ACT = re.compile(
    r"^\W*(no\b|not\b|none\b|nil\b|unknown\b|n/?a\b|unverified\b|cannot\b|could not\b)", re.I
)


def code_key(code: str) -> str:
    """ "UPD 1a" / "UPD-1a" / "upd1a" -> "UPD1A"."""
    return re.sub(r"[\s\-]", "", code or "").upper()


@dataclass(frozen=True)
class Requirement:
    code: str
    level: str
    zero_kind: str  # absence | condition | mixed | none
    groups: tuple  # tuple of tuples of tags: every group needs one of its tags
    check: str = ""
    evidence: str = ""
    zero_sentences: tuple = ()
    scan: tuple = ()  # regular expressions; a passage matching all of them blocks an absence zero
    review_status: str = "draft"
    needs_decision: bool = False
    why: str = ""
    note: str = ""

    @property
    def has_zero_rule(self) -> bool:
        return self.zero_kind != "none"

    @property
    def law_policy(self) -> bool:
        return cutoff.is_law_policy(self.level)


@dataclass(frozen=True)
class Table:
    requirements: dict  # code_key -> Requirement
    legal_base_overrides: dict  # agency ID -> "act" | "constitution"


@lru_cache(maxsize=4)
def _load(path: str) -> Table:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rows = {}
    for row in data.get("questions") or []:
        req = Requirement(
            code=str(row["code"]),
            level=str(row.get("level") or ""),
            zero_kind=str(row.get("zero_kind") or "none"),
            groups=tuple(tuple(str(t) for t in g) for g in (row.get("requires") or [])),
            check=str(row.get("check") or ""),
            evidence=str(row.get("evidence") or ""),
            zero_sentences=tuple(str(s) for s in (row.get("zero_sentences") or [])),
            scan=tuple(str(p) for p in (row.get("scan") or [])),
            review_status=str(row.get("review_status") or "draft"),
            needs_decision=bool(row.get("needs_decision")),
            why=str(row.get("why") or ""),
            note=str(row.get("note") or ""),
        )
        rows[code_key(req.code)] = req
    overrides = {
        str(k).upper(): str(v).lower() for k, v in (data.get("legal_base_overrides") or {}).items()
    }
    return Table(rows, overrides)


def load(path: Path | None = None) -> Table:
    return _load(str(path or TABLE_PATH))


def required_for(code: str, table: Table | None = None) -> Requirement | None:
    """The requirement row of a question code, or None when the table has no row for it."""
    return (table or load()).requirements.get(code_key(code))


# -- the agency's legal basis -----------------------------------------------------------------------
def legal_base_kind(parastatal: Parastatal, table: Table | None = None) -> str:
    """ "act" when the agency has a parent Act, "constitution" when its legal basis is a
    constitution document. Read from the Governing Act text (the discovery agent writes it, the
    team may edit it). A blank text, "No parent Act located", "Not established" or a general law
    (Companies Act, Societies Registration Act) means "constitution": the question then needs the
    constitution document, never the general law."""
    table = table or load()
    forced = table.legal_base_overrides.get(parastatal.id.upper())
    if forced in ("act", "constitution"):
        return forced
    text = (parastatal.governing_act or "").strip()
    if not text:
        return "constitution"
    lead = re.split(r"[;(\[]|\.\s|\n", text, maxsplit=1)[0]
    if _NO_ACT.match(lead) or not re.search(r"\bact\b", lead, re.I):
        return "constitution"
    return "constitution" if _GENERAL_LAWS.search(lead) else "act"


# -- the tags of a Citation Sheet row ----------------------------------------------------------------
def tags_of(source: Source) -> set[str]:
    tags = {_SYNONYMS.get(t.upper(), t.upper()) for t in _TAG.findall(source.useful_for or "")}
    if (source.source_type or "").strip().lower() == "official website":
        tags.add("WEB")  # the website row Step 1 adds for each agency has no [WEB] tag
    return tags


def _usable(source: Source) -> bool:
    """Reviewed, verified and its saved text is on disk (the rule Step 2 uses)."""
    return (
        source.use_for_answers
        and source.verification_status == "Verified"
        and bool(source.content_path)
        and Path(source.content_path).exists()
    )


def _is_home(source: Source) -> bool:
    """The agency's home page row: the "Official website" row, or a page at the root of its site."""
    path = urlsplit(source.url or "").path
    return (source.source_type or "").strip().lower() == "official website" or path in ("", "/")


def crawl_status(parastatal: Parastatal, sources: list[Source]) -> tuple[str, str]:
    """("complete" | "incomplete" | "none", the marker text) of the agency's site crawl, read from
    the Notes of its own-site rows (Step 1 writes "SITE-CRAWL: complete, 12 of 12 links." on the
    home page row). "none": the crawl has not run for this agency."""
    own_site = site_of(parastatal.official_website)
    state, text = "none", ""
    for s in sources:
        if own_site and site_of(s.url) == own_site:
            m = re.search(
                rf"{SITE_CRAWL}: (complete|incomplete)[^\n]*?(?:\.(?=\s|$)|$)", s.notes or ""
            )
            if m:
                state, text = m.group(1), m.group(0)
    return state, text


# -- the check ----------------------------------------------------------------------------------------
@dataclass
class Gate:
    state: str  # no_rule | allowed | missing | unreadable
    present: dict = field(default_factory=dict)  # tag -> usable Citation IDs
    missing: list = field(default_factory=list)  # tags with no row at all, or none in force
    unreadable: list = field(default_factory=list)  # Citation IDs tagged but failed to open
    rows: list = field(default_factory=list)  # the usable required rows (Source objects)
    after_cutoff: list = field(default_factory=list)  # Citation IDs dated after the cut-off
    # One entry per required group: (document label, "present" | "missing" | "did not open", IDs)
    detail: list = field(default_factory=list)

    def missing_text(self) -> str:
        names = []
        for tag in self.missing:
            name = DOCUMENT_NAMES.get(tag, tag)
            if name not in names:
                names.append(name)
        return "; ".join(names)


def _resolve(group: tuple, kind: str) -> tuple:
    """The tags of a group, with LEGAL_BASE turned into the Act or the constitution document."""
    legal = "ACT" if kind == "act" else "CONSTITUTION"
    return tuple(legal if tag == "LEGAL_BASE" else tag for tag in group)


def check(
    req: Requirement | None,
    parastatal: Parastatal,
    sources: list[Source],
    *,
    rule=None,
    table: Table | None = None,
) -> Gate:
    """May a 0 be given for this question and agency, as far as the sources go?

    `sources` is every Citation Sheet row of the agency plus the shared "All parastatals" rows,
    usable or not. Present = a usable row carries one tag of the group. A group with only rows that
    failed to open is "unreadable" (a person must open them); a group with no row, or none in force
    at the Law/Policy cut-off, is "missing"."""
    if req is None or not req.has_zero_rule or not req.groups:
        return Gate("no_rule")
    kind = legal_base_kind(parastatal, table)
    own_site = site_of(parastatal.official_website)
    usable = [s for s in sources if _usable(s)]
    screen = cutoff.screen_sources(usable, rule, req.law_policy and rule is not None)
    in_force = {id(s) for s in screen.usable}
    gate = Gate("allowed", after_cutoff=sorted(set(screen.later + screen.bills)))
    seen: set[int] = set()
    for group in req.groups:
        wanted = set(_resolve(group, kind))
        found, failed, late = [], [], False
        if "WEBPAGE" in wanted and crawl_status(parastatal, sources)[0] != "complete":
            # The extra website pages count only when every menu link of the home page was
            # captured: an incomplete or missing crawl can never show that something is not on the site.
            gate.missing.append("SITECRAWL")
            gate.detail.append(("SITECRAWL", "missing", []))
            continue
        for s in sources:
            tags = tags_of(s)
            if "WEBPAGE" in wanted:
                hit = (
                    bool(tags & WEBPAGE_TAGS)
                    and bool(own_site)
                    and site_of(s.url) == own_site
                    and not _is_home(s)
                )
            else:
                hit = bool(tags & wanted)
            if not hit:
                continue
            if id(s) in in_force:
                found.append(s)
            elif _usable(s):
                late = True  # in the sheet but dated after the cut-off
            else:
                failed.append(s)
        label = sorted(wanted)[0] if wanted else "?"
        gate.detail.append(
            (
                label,
                "present" if found else "did not open" if failed and not late else "missing",
                [s.citation_id for s in (found or failed)],
            )
        )
        if found:
            gate.present[label] = [s.citation_id for s in found]
            for s in found:
                if id(s) not in seen:
                    seen.add(id(s))
                    gate.rows.append(s)
        elif failed and not late:
            gate.unreadable += [s.citation_id for s in failed]
        else:
            gate.missing.append(label)
    if gate.missing:
        gate.state = "missing"
    elif gate.unreadable:
        gate.state = "unreadable"
    return gate


# -- the full-text scan -------------------------------------------------------------------------------
@dataclass
class Hit:
    citation_id: str
    page: str
    passage: str


@dataclass
class Scan:
    hits: list = field(default_factory=list)
    scanned: list = field(default_factory=list)  # Citation IDs read in full
    patterns: tuple = ()

    @property
    def clear(self) -> bool:
        return not self.hits


_PAGE = re.compile(r"(?m)^\[page (\d+)\]\s*$")
WINDOW, STEP, MAX_HITS_PER_SOURCE, MAX_PASSAGE = 700, 450, 6, 600


def _passages(text: str):
    """(page, passage) pieces of a document: blank-line blocks, long blocks cut into overlapping
    windows. The page comes from the "[page N]" markers a PDF's text has."""
    page = ""
    for block in re.split(r"\n\s*\n", text):
        m = _PAGE.findall(block)
        if m:
            page = m[-1]
        block = _PAGE.sub(" ", block).strip()
        if not block:
            continue
        if len(block) <= WINDOW:
            yield page, block
            continue
        for start in range(0, len(block), STEP):
            yield page, block[start : start + WINDOW]
            if start + WINDOW >= len(block):
                break


def scan_text(text: str, patterns: tuple, citation_id: str = "") -> list[Hit]:
    """Passages in `text` that match EVERY pattern (case-insensitive)."""
    compiled = [re.compile(p, re.I) for p in patterns]
    if not compiled:
        return []
    hits = []
    for page, passage in _passages(text):
        if all(c.search(passage) for c in compiled):
            hits.append(Hit(citation_id, page, re.sub(r"\s+", " ", passage)[:MAX_PASSAGE]))
            if len(hits) >= MAX_HITS_PER_SOURCE:
                break
    return hits


def scan_required(req: Requirement, rows: list[Source]) -> Scan:
    """Read the whole saved text of every required document and collect the passages that match the
    question's scan patterns. Run before any absence-based zero: a hit blocks the zero."""
    result = Scan(patterns=req.scan)
    for s in rows:
        if not s.content_path or not Path(s.content_path).exists():
            continue
        text = Path(s.content_path).read_text(encoding="utf-8")
        result.scanned.append(s.citation_id)
        result.hits += scan_text(text, req.scan, s.citation_id)
    return result


# -- check and scan together --------------------------------------------------------------------------
@dataclass
class ZeroDecision:
    state: str  # allowed | blocked_by_scan | missing | unreadable | no_rule
    gate: Gate
    scan: Scan | None
    note: str

    @property
    def allowed(self) -> bool:
        return self.state == "allowed"


def decide_zero(
    req: Requirement | None,
    parastatal: Parastatal,
    sources: list[Source],
    *,
    rule=None,
    table: Table | None = None,
) -> ZeroDecision:
    """May an absence-based zero be given? The note is what to write in the answer's notes."""
    gate = check(req, parastatal, sources, rule=rule, table=table)
    if gate.state == "no_rule":
        return ZeroDecision("no_rule", gate, None, "")
    if gate.state == "missing":
        extra = (
            f" Dated after the cut-off: {', '.join(gate.after_cutoff)}."
            if gate.after_cutoff
            else ""
        )
        return ZeroDecision("missing", gate, None, f"Missing: {gate.missing_text()}.{extra}")
    if gate.state == "unreadable":
        return ZeroDecision(
            "unreadable",
            gate,
            None,
            "Required source did not open: "
            + ", ".join(gate.unreadable)
            + ". Human verification required.",
        )
    checked = ", ".join(f"{s.citation_id} ({s.title[:60]})" for s in gate.rows)
    if not req.scan:  # a condition-only zero: no "nothing found" claim to scan for
        return ZeroDecision("allowed", gate, None, f"Checked: {checked}.")
    scan = scan_required(req, gate.rows)
    if scan.hits:
        first = scan.hits[0]
        ids = sorted({h.citation_id for h in scan.hits})
        return ZeroDecision(
            "blocked_by_scan",
            gate,
            scan,
            f"Blocked: relevant text found in {', '.join(ids)} (for example page {first.page or '?'}: "
            f"“{first.passage[:200]}”).",
        )
    return ZeroDecision("allowed", gate, scan, f"Checked: {checked}. Scanned in full: no match.")


# -- what Step 1 is told, and what counts as covered --------------------------------------------------
_NOT_CHECK = re.compile(r"^\W*(part [ab]\b|\[?note\b)", re.I)
SHARED_ONLY = frozenset({"TCP", "ULG-LAW"})  # the laws searched once for every agency of a city


def check_line(question) -> str:
    """The first line of a question's methodology: the "Check ..." sentence that says where to look.
    Empty for a methodology that starts with "Part A:" or a note (the Evidence column says it)."""
    for line in (question.methodology or "").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            return "" if _NOT_CHECK.match(line) else line[:320]
    return ""


def requires_text(
    req: Requirement | None, parastatal: Parastatal | None = None, *, only=None
) -> str:
    """The documents a question needs, for the finder: "parent Act [ACT]; Rules [RULES]; ...".
    `parastatal` turns the legal basis into the Act or the constitution document; without it the
    text names both. `only`: keep the groups made of these tags only (the shared laws search)."""
    if req is None or not req.has_zero_rule or not req.groups:
        return ""
    kind = legal_base_kind(parastatal) if parastatal is not None else None
    names = []
    for group in req.groups:
        tags = [t for t in group if t != "WEBPAGE"] or ["WEBPAGE"]
        if kind is None and "LEGAL_BASE" in tags:
            name = f"{DOCUMENT_NAMES['ACT']} or, for an agency with no parent Act, {DOCUMENT_NAMES['CONSTITUTION']}"
        else:
            name = DOCUMENT_NAMES.get(_resolve(tuple(tags), kind or "act")[0], tags[0])
        if only is not None and not set(_resolve(tuple(tags), kind or "act")) <= set(only):
            continue
        if name not in names:
            names.append(name)
    return "; ".join(names)


def digest_lines(question, parastatal: Parastatal | None = None, *, only=None) -> list[str]:
    """The extra lines the finder gets for one question: its Check sentence and Requires list."""
    req = required_for(question.id)
    required = requires_text(req, parastatal, only=only)
    if only is not None and not required:
        return []  # the shared-laws search is told only about questions that need a shared law
    lines = []
    if check := check_line(question):
        lines.append(f"  Check: {check}")
    if required:
        lines.append(f"  Requires: {required}")
    return lines


def legal_base_line(parastatal: Parastatal) -> str:
    """One line for the finder about the agency's legal basis."""
    if legal_base_kind(parastatal) == "constitution":
        return (
            "Legal basis: NO parent Act (a company or society). Find its constitution document "
            f"({DOCUMENT_NAMES['CONSTITUTION']}) instead of a parent Act; a general Companies Act "
            "or Societies Registration Act is not its Act.\n"
        )
    return "Legal basis: statutory, so the parent Act [ACT] and its Rules [RULES] are required.\n"


def requirement_note(question_ids, parastatal: Parastatal | None = None, limit: int = 5) -> str:
    """For the source assessor: what the questions this source was found for require."""
    seen, lines = set(), []
    for qid in question_ids or []:
        req = required_for(qid)
        if req is None or code_key(qid) in seen or not req.has_zero_rule:
            continue
        seen.add(code_key(qid))
        lines.append(
            f"- {req.code}: requires {requires_text(req, parastatal)}. Evidence: {req.evidence}"
        )
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def coverage(
    questions, parastatal: Parastatal, sources: list[Source], *, rule=None
) -> tuple[set, dict, dict]:
    """(covered question IDs, {missing tag: [question IDs]}, {unopened Citation ID: [question IDs]}).

    A question with a zero rule is covered when every required group has a usable row of the agency
    or a shared row. A question without one (or without a table row) is left out of all three: the
    caller keeps its own rule for it."""
    covered, missing, unopened = set(), {}, {}
    for q in questions:
        req = required_for(q.id)
        if req is None or not req.has_zero_rule or not req.groups:
            continue
        gate = check(req, parastatal, sources, rule=rule)
        if gate.state == "allowed":
            covered.add(q.id)
        for tag in gate.missing:
            missing.setdefault(tag, []).append(q.id)
        for cid in gate.unreadable:
            unopened.setdefault(cid, []).append(q.id)
    return covered, missing, unopened


def has_rule(question) -> bool:
    req = required_for(question.id)
    return req is not None and req.has_zero_rule and bool(req.groups)


# -- the lines added to the Step 2 and Step 3 messages ------------------------------------------------
MAX_PASSAGES = 5


def zero_block(req: Requirement | None, decision: "ZeroDecision | None", *, step: int = 2) -> str:
    """The question's zero condition, what the agency's sources allow, and any scan hits, as lines for
    the model. The methodology's zero condition has precedence over any other zero rule in the prompts."""
    if req is None:
        return ""
    if not req.has_zero_rule:
        return (
            "ZERO CONDITION: the methodology states none for this question. Do not give a score of 0 "
            "for something that was not found: leave the score blank and say what is missing.\n"
        )
    sentences = " / ".join(req.zero_sentences) or "(read it in the Detailed Methodology)"
    lines = [
        f"ZERO CONDITION (from the methodology): {sentences}",
        "PRECEDENCE: this zero condition from the methodology overrides any other rule about a score "
        "of 0, absence or 'not found' in your instructions.",
    ]
    if decision is None:
        return "\n".join(lines) + "\n"
    ids = ", ".join(s.citation_id for s in decision.gate.rows)
    if decision.state == "allowed":
        scanned = (
            "Code scanned the full text of each: no passage matched the question's key terms."
            if decision.scan is not None
            else "This zero rests on what the provisions say, not on nothing being found, so no scan was run."
        )
        how = (
            'If nothing in these sources meets the methodology\'s test, the score is 0: set "zero_checked" '
            'true, "proposed_score" 0, "sufficiency" "sufficient" and "evidence_excerpt" "" (the code '
            "records what was checked). If a provision you can quote puts the answer in a band, score "
            'that band and quote it as usual, with "zero_checked" false.'
            if step == 2
            else "A zero is allowed. If Step 2's answer is marked ZERO-CHECKED, the quote may be empty; "
            "cite one of the sources listed here. If a provision you can quote puts the answer in a "
            "band, score that band and quote it as usual."
        )
        lines += [
            f"REQUIRED SOURCES: every one is in the Citation Sheet and was read: {ids}. {scanned}",
            how,
        ]
    elif decision.state == "blocked_by_scan":
        lines.append(
            f"REQUIRED SOURCES: all present ({ids}). SCAN FOUND (full text of the required "
            "documents; a 0 for 'nothing found' is NOT allowed while these stand):"
        )
        for hit in decision.scan.hits[:MAX_PASSAGES]:
            where = f" p.{hit.page}" if hit.page else ""
            lines.append(f"  [{hit.citation_id}{where}] {hit.passage}")
        lines.append(
            "Decide from these passages: if they put the answer in a band of the methodology, score "
            "that band and quote the decisive sentence word for word; if they do not, leave the score "
            "blank and say why."
        )
    elif decision.state == "missing":
        lines += [
            f"REQUIRED SOURCES: MISSING: {decision.gate.missing_text()}.",
            "A score of 0 is NOT allowed for this question and agency. Give a positive score only if "
            "the sources provided support it with a quote; otherwise leave the score blank and say "
            '"Missing: <the document>".',
        ]
    else:  # unreadable
        lines += [
            f"REQUIRED SOURCES: in the Citation Sheet but did not open: {', '.join(decision.gate.unreadable)}.",
            "A score of 0 is NOT allowed until a person opens them. Give a positive score only if the "
            "sources provided support it with a quote; otherwise leave the score blank.",
        ]
    return "\n".join(lines) + "\n"


# -- an audit line for a zero the AI wrote (the Compare workbook's "AI zeros" sheet) -----------------
GATE_WORDS = {
    "allowed": "allowed",
    "blocked_by_scan": "blocked by the scan",
    "missing": "required source missing",
    "unreadable": "required source did not open",
    "no_rule": "no zero condition in the methodology",
}


def audit_zero(
    req: Requirement | None, parastatal: Parastatal, sources: list[Source], *, rule=None
) -> dict:
    """What the gate says about a zero today, in words: {"gate", "documents", "scan"}. It reads the
    Citation Sheet as it is now, not as it was when the zero was written."""
    if req is None:
        return {"gate": "no row in the requirements table", "documents": "", "scan": ""}
    decision = decide_zero(req, parastatal, sources, rule=rule)
    if decision.state == "no_rule":
        return {"gate": GATE_WORDS["no_rule"], "documents": "", "scan": "not applicable"}
    documents = "; ".join(
        f"{DOCUMENT_NAMES.get(label, label)}: "
        + (
            f"{status} ({', '.join(ids)})"
            if ids
            else status.upper()
            if status != "present"
            else status
        )
        for label, status, ids in decision.gate.detail
    )
    if decision.state in ("missing", "unreadable"):
        scan = "not run: a required source is missing or did not open"
    elif decision.scan is None:
        scan = "not needed: the zero rests on what a provision says"
    elif decision.scan.hits:
        first = decision.scan.hits[0]
        ids = sorted({h.citation_id for h in decision.scan.hits})
        scan = (
            f"{len(decision.scan.hits)} passage(s) found in {', '.join(ids)}; first"
            f"{' p.' + first.page if first.page else ''}: \u201c{first.passage[:200]}\u201d"
        )
    else:
        scan = f"scanned in full ({', '.join(decision.scan.scanned)}): no match"
    return {
        "gate": GATE_WORDS.get(decision.state, decision.state),
        "documents": documents,
        "scan": scan,
    }
