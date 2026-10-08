---
name: parastatal
title: Parastatal
code: PARASTATAL
# What is assessed in each city: the parastatal agencies Step 1 discovers.
unit: parastatal
question_bank: data/question_banks/Parastatal_ASICS_Question_Bank.xlsx
# City folders: outputs/cities/<City>/ ("." = the outputs folder itself)
outputs: .
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
sections) for each agency; Step 3 scores each answer in the Parastatal scoring workbook, one
row per city and agency.
