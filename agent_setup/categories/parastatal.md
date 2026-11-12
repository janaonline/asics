---
name: parastatal
title: Parastatal
scoring_code: PARASTATAL
# What is assessed in each city: the parastatal agencies Step 1 discovers.
unit: parastatal
question_bank: data/question_banks/Parastatal_ASICS_Question_Bank.xlsx
# This category's folder inside outputs/: outputs/Parastatal/cities/<City>/
outputs: Parastatal
# Scored in copies of the team's templates, one file per section (Step 3 fills a copy of each).
scoring_templates:
  - scoring/2027/templates/Parastatal_UPD_Template.xlsx
  - scoring/2027/templates/Parastatal_SC_Template.xlsx
  - scoring/2027/templates/Parastatal_DPG_Template.xlsx
# Law/Policy questions may only use sources that took effect on or before this date. A later
# source stays in the Citation Sheet and can still be used for Implementation questions.
law_cutoff: 2026-08-31
# A source whose effective date is unknown: "confirm" (use it with a CONFIRM note, Confidence at
# most Medium) or "block" (treat it like a later source).
undated_law_policy: confirm
shared_rules: shared-rules
steps:
  1:
    discover: parastatal-discovery
    profile: website-profiler
    sources: citation-builder
    assess: source-assessor
  2:
    answer: answer-writer
  3:
    score: question-scorer
---
The parastatal agencies that serve each city: water supply entities, public bus transport operators,
development authorities and others. Step 1 discovers them, checks each one's official website
and builds its Citation Sheet; Step 2 answers the Parastatal question bank (UPD, DPG and SC
sections), each applicable question separately for every parastatal; Step 3 fills a copy of each of the team's UPD, SC and DPG
scoring templates, one row per city and parastatal.
