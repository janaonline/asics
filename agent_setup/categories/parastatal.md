---
name: parastatal
title: Parastatal
scoring_code: PARASTATAL
# What is assessed in each city: the parastatal agencies Step 1 discovers.
unit: parastatal
question_bank: data/question_banks/Parastatal_ASICS_Question_Bank.xlsx
# This category's folder inside outputs/: outputs/Parastatal/cities/<City>/
outputs: Parastatal
scoring_workbook: scoring/2027/templates/ASICS_2027_Parastatal_Scoring_Workbook_DRAFT.xlsx
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
The parastatal agencies that serve each city: water supply boards, transport corporations,
development authorities and others. Step 1 discovers them, checks each one's official website
and builds its Citation Sheet; Step 2 answers the Parastatal question bank (UPD, DPG and SC
sections), each applicable question separately for every parastatal; Step 3 scores each answer in the Parastatal scoring workbook, one
row per city and agency.
