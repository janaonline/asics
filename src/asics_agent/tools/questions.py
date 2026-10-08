from pydantic import BaseModel, Field

from asics_agent.tools.base import ClientTool, ToolContext, register


class Args(BaseModel):
    question_id: str = Field(description="A question ID, e.g. UPD 1a")


def run(ctx: ToolContext, question_id: str) -> str:
    if not ctx.questions:
        from asics_agent.verticals import load_bank

        ctx.questions, _ = load_bank(ctx.services.settings)
    wanted = question_id.replace("-", " ").strip().upper()
    q = next(
        (
            q
            for q in ctx.questions.values()
            if q.id.upper() == wanted or q.raw_id.upper() == question_id.strip().upper()
        ),
        None,
    )
    if q is None:
        return f"No question {question_id!r} in the question bank."
    return (
        f"{q.raw_id} [{q.tag}, max score {q.max_score}] {q.text}\n"
        f"Assessment level: {q.assessment_level}\nApplies to: {q.applicability}\n"
        f"Detailed Methodology:\n{q.methodology}"
    )


register(ClientTool(name="lookup_question", args=Args, run=run))
