"""Plain-language summaries for the research team (used by the app, CLI and workbook)."""

from collections import Counter

from asics_agent.models import Answer, Issue

# What each Status means, and what a reviewer should do about it.
STATUS_HELP: dict[str, tuple[str, str]] = {
    "Answered — Verified Source": (
        "Answered from a Citation Sheet source (see Citation ID) that opened properly and "
        "contains the quote.",
        "Open the link, find the quote, and confirm the answer and score.",
    ),
    "Partially Answered": (
        "The evidence answers only part of the question.",
        "Read the Notes to see what is missing; look for more evidence if needed.",
    ),
    "Insufficient Evidence": (
        "No source in the Citation Sheet answers this question. No answer or score was given. "
        "The Notes say what kind of source would answer it.",
        "Add a source to the Citation Sheet in the Sources workbook and run Step 2 again, or "
        "accept that none is published.",
    ),
    "Human Verification Required": (
        "An answer was drafted, but something could not be confirmed automatically "
        "(for example, the quote wasn't found on the page).",
        "Check this one carefully before accepting it.",
    ),
    "Computed from Sub-indicators": (
        "The total of this main question's sub-questions, as the methodology says.",
        "Review the sub-questions; this total follows from them.",
    ),
    "Not Applicable": (
        "The question bank says this question doesn't apply to this type of parastatal.",
        "Nothing to do, unless the parastatal type is wrong.",
    ),
    "Not Yet Assessed": (
        "The question applies but wasn't researched in this run (a checks-only or filtered run).",
        "Run it again including this question.",
    ),
}

VERIFICATION_HELP = {
    "Verified": "The exact link opened in a normal web request and shows real, readable "
    "content that supports what it is listed for.",
    "Human Verification Required": "The link may work, but the automatic check couldn't "
    "confirm it (e.g. the page needs JavaScript, is a scanned PDF, or redirects to another "
    "site). A person should open it.",
    "Not verified": "The link didn't open, returned an error, showed only metadata "
    "(common with India Code), or didn't support its stated use. It is not used for answers.",
}

NEEDS_REVIEW = {"Human Verification Required", "Partially Answered", "Insufficient Evidence"}


def team_issues(issues: list[Issue]) -> list[Issue]:
    """Team-facing issues, most important first, without duplicates."""
    order = {"error": 0, "warning": 1, "info": 2}
    seen, result = set(), []
    for issue in sorted(issues, key=lambda i: order[i.severity]):
        if issue.audience == "team" and issue.message not in seen:
            seen.add(issue.message)
            result.append(issue)
    return result


def severity_label(severity: str) -> str:
    return {"error": "Must fix", "warning": "Please check", "info": "For your information"}[
        severity
    ]


def answer_summary(answers: list[Answer]) -> list[tuple[str, int, str]]:
    """[(status, count, what it means)] in a fixed, readable order."""
    counts = Counter(a.status for a in answers)
    return [(s, counts[s], STATUS_HELP[s][0]) for s in STATUS_HELP if counts.get(s)]


def headline(answers: list[Answer], issues: list[Issue]) -> str:
    skipped = {"Not Applicable", "Not Yet Assessed", "Computed from Sub-indicators"}
    researched = [
        a for a in answers if a.status not in skipped and a.source_used != "Sub-indicators"
    ]
    if not researched:
        return "Checks finished. No questions were researched in this run."
    answered = sum(a.status.startswith("Answered") for a in researched)
    review = sum(a.status in NEEDS_REVIEW for a in researched)
    must_fix = sum(i.severity == "error" for i in team_issues(issues))
    text = (
        f"{answered} of {len(researched)} questions answered with a checked source; "
        f"{review} need a person to look at them."
    )
    if must_fix:
        text += f" {must_fix} problem(s) must be fixed; see Needs Attention."
    return text
