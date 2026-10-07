"""Final QA: the checklist from the source prompt, run in code, for each step.

Step 1 (Sources): every link was found by a tool (or added by the team), was opened and
tested, and nothing unverified keeps a score.
Step 2 (Answers): every question has a status and useful notes, and every answer cites a
Citation Sheet row that exists, is marked for use, and is verified.
"""

import re

from asics_agent.links.accessibility import is_india_code
from asics_agent.models import Answer, Issue, Source

GENERIC_NOTES = re.compile(r"^\s*(source checked|checked|n/?a|ok|done|verified)\.?\s*$", re.I)


def _flag(issues: list[Issue], severity: str, message: str, ref: str | None = None) -> None:
    issues.append(
        Issue(phase="final_qa", severity=severity, message=message, ref=ref, audience="team")
    )


def qa_sources(sources: list[Source], tool_urls: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    for s in sources:
        ref = s.citation_id or f"{s.parastatal_id}: {s.url}"
        if s.provenance in {"web_search", "fetched_page"} and s.url not in tool_urls:
            _flag(
                issues,
                "error",
                "This link was not found by a search in this run, so it may "
                "be made up. Remove it or check it by hand.",
                ref,
            )
        if not s.checked_at:
            _flag(issues, "error", "This link was never opened to check it. Check it by hand.", ref)
        if s.verification_status != "Verified" and (
            s.authority_score > 0 or s.accessibility == "Public"
        ):
            _flag(
                issues,
                "error",
                "This link could not be opened, but it still has a score or "
                "is marked Public. Correct it.",
                ref,
            )
        if is_india_code(s.url) and s.verification_status == "Verified":
            _flag(
                issues,
                "warning",
                "India Code link passed the automatic check. Open it once "
                "to confirm it shows the text of the Act.",
                ref,
            )
        if not s.notes.strip():
            _flag(issues, "error", "This source has no Notes. Add a short explanation.", ref)
    if not any(i.severity == "error" for i in issues):
        _flag(
            issues,
            "info",
            "Final checks passed: every link was found by a search or added "
            "by your team, and every link was opened and checked.",
        )
    return issues


def qa_answers(
    answers: list[Answer], citations: list[Source], applicability: dict[str, list[str]]
) -> list[Issue]:
    issues: list[Issue] = []
    usable = {
        s.citation_id: s
        for s in citations
        if s.use_for_answers and s.verification_status == "Verified"
    }
    answered = {(a.parastatal_id, a.question_id): a for a in answers}
    for parastatal_id, question_ids in applicability.items():
        for qid in question_ids:
            ref = f"{parastatal_id}/{qid}"
            a = answered.get((parastatal_id, qid))
            if a is None:
                _flag(issues, "error", "This question has no answer row.", ref)
                continue
            if not a.status:
                _flag(issues, "error", "This question has no Status.", ref)
            if len(a.notes.strip()) < 30 or GENERIC_NOTES.match(a.notes):
                _flag(issues, "error", "This question's Notes are missing or too vague.", ref)
            if a.source_used == "Sub-indicators":
                continue
            if a.citation_id and a.citation_id not in usable:
                _flag(
                    issues,
                    "error",
                    f"The answer cites {a.citation_id}, which is not a "
                    "verified Citation Sheet row marked for use.",
                    ref,
                )
            elif a.citation_id and a.citation_url != usable[a.citation_id].url:
                _flag(
                    issues,
                    "error",
                    f"The answer's link doesn't match {a.citation_id}'s link "
                    "in the Citation Sheet.",
                    ref,
                )
            if a.status.startswith("Answered") and not a.citation_id:
                _flag(issues, "error", "Marked as answered but doesn't name its Citation ID.", ref)
    if not any(i.severity == "error" for i in issues):
        _flag(
            issues,
            "info",
            "Final checks passed: every question has a status and notes, and "
            "every answer cites a checked Citation Sheet row.",
        )
    return issues
