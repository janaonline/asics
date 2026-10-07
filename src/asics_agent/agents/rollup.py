"""Computes MQ scores from their sub-questions, only where the methodology says to sum.

Source prompt: "Do not calculate scores unless the workbook methodology explicitly
requires it."
"""

from asics_agent.models import Answer, Question


def compute_rollups(
    questions: dict[str, Question], applicability: dict[str, list[str]], answers: list[Answer]
) -> list[Answer]:
    by_key = {(a.parastatal_id, a.question_id): a for a in answers}
    rollups = []
    for parastatal_id, question_ids in applicability.items():
        for qid in question_ids:
            mq = questions[qid]
            if not mq.is_rollup:
                continue
            children = [c for c in mq.children if c in question_ids]
            if not children:
                continue
            child_answers = [by_key.get((parastatal_id, c)) for c in children]
            if "sum" not in mq.methodology.lower():
                rollups.append(
                    Answer(
                        parastatal_id=parastatal_id,
                        question_id=qid,
                        status="Human Verification Required",
                        source_used="Sub-indicators",
                        notes="Not computed: the methodology does not state how sub-questions "
                        f"({', '.join(children)}) are combined. Review them and score manually.",
                    )
                )
                continue
            scored = [a for a in child_answers if a and a.proposed_score is not None]
            max_total = sum(questions[c].max_score or 0 for c in children)
            parts = "; ".join(
                f"{c}: {a.proposed_score:g}"
                if a and a.proposed_score is not None
                else f"{c}: no score ({a.status if a else 'not answered'})"
                for c, a in zip(children, child_answers, strict=True)
            )
            complete = len(scored) == len(children)
            rollups.append(
                Answer(
                    parastatal_id=parastatal_id,
                    question_id=qid,
                    proposed_score=sum(a.proposed_score for a in scored) if scored else None,
                    status="Computed from Sub-indicators" if complete else "Partially Answered",
                    source_used="Sub-indicators",
                    answer=f"Sum of applicable sub-indicators (maximum {max_total:g} of "
                    f"{mq.max_score or 0:g} for this parastatal type).",
                    notes=f"Components — {parts}."
                    + ("" if complete else " Incomplete: some sub-questions have no score."),
                )
            )
    return rollups
