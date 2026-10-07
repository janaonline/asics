import re

from asics_agent.agents.sections.base import SectionSpec, register
from asics_agent.agents.state import AnswerTask
from asics_agent.models import Answer


def require_figures(answer: Answer, task: AnswerTask) -> Answer:
    """Numeric questions must show the figures they were computed from."""
    level = task["question"].assessment_level or ""
    if (
        "Numeric" in level
        and answer.status.startswith("Answered")
        and not re.search(r"\d", answer.answer)
    ):
        return answer.model_copy(
            update={
                "status": "Human Verification Required",
                "notes": answer.notes
                + " Numeric question answered without the underlying figures.",
            }
        )
    return answer


# Guidance for this section is in agent_setup/skills/sections/sc.md; this adds a code check.
register(SectionSpec(code="SC", postprocess=require_figures))
