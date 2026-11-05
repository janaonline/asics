"""How a saved question id relates to the question bank in use now.

Old answers files and scoring workbooks may name questions the bank no longer has ("retired
questions"), or use an id that now means a different question. They are shown with a plain note,
never as an error: `BankContext.flag` says which case a row is in.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from asics_agent.models import Question
from asics_agent.question_bank import load_question_bank
from asics_agent.scoring.template_import import normalise_code

RETIRED = "retired question"
NOT_IN_BANK = "question not in this bank version"
CHANGED = "question changed since this was written"


@dataclass
class BankContext:
    bank: dict[str, Question]  # the bank in use, by normalised code
    retired: dict[str, Question] = field(default_factory=dict)  # codes only earlier banks had
    raw_to_code: dict[str, str] = field(default_factory=dict)  # a bank's own id -> normalised
    old_raw_to_code: dict[str, str] = field(default_factory=dict)  # same, earlier banks only

    def code_for_raw(self, raw: str) -> tuple[str | None, bool]:
        """(normalised code, found in the bank in use) for an id as a saved file spells it."""
        if raw in self.raw_to_code:
            return self.raw_to_code[raw], True
        if raw in self.old_raw_to_code:  # an earlier bank's own spelling ("DPG d")
            return self.old_raw_to_code[raw], False
        norm = normalise_code(raw)
        return (norm, norm in self.bank) if norm else (None, False)

    def flag(self, raw_id: str, question_text: str = "") -> str:
        """ "" when the row is about a question the bank still asks; else a short plain note."""
        from asics_agent.scoring.ai import same_question

        code, _ = self.code_for_raw(str(raw_id))
        if code is None:
            return NOT_IN_BANK
        if code not in self.bank:
            return RETIRED if code in self.retired else NOT_IN_BANK
        if question_text and not same_question(question_text, self.bank[code].text):
            return CHANGED
        return ""


def archived_banks(bank_file: Path):
    """(path, questions) of every earlier bank kept in the bank folder's archive/."""
    for path in sorted((Path(bank_file).parent / "archive").glob("*.xlsx")):
        questions, _ = load_question_bank(path)
        yield path, questions


def build_context(bank: dict[str, Question], bank_file: Path) -> BankContext:
    ctx = BankContext(bank, raw_to_code={q.raw_id: q.id for q in bank.values()})
    current_raw = set(ctx.raw_to_code)
    for _, questions in archived_banks(bank_file):
        for q in questions.values():
            if q.id not in bank:
                ctx.retired.setdefault(q.id, q)
            if q.raw_id not in current_raw:
                ctx.old_raw_to_code.setdefault(q.raw_id, q.id)
    return ctx


@lru_cache
def _context_for(settings) -> BankContext:
    from asics_agent.categories import load_bank

    return build_context(load_bank(settings)[0], settings.question_bank)


def context_for(settings) -> BankContext:
    """The context for a category's settings (cached; settings objects are hashable)."""
    return _context_for(settings)
