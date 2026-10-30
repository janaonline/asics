---
name: ulg
title: ULG
# The scoring workbook's code: it names UPD_ai.xlsx, the UPD sheets and the scoring runs.
# (Interim: the ULG category has only the UPD section today. SC and DPG will be added.)
scoring_code: UPD
# What is assessed in each city: the urban local government (ULG) itself, under its state's laws.
# One unit per city, answered once per city.
unit: ulg
# The ULG question list is a sheet of the UPD scoring workbook; its columns have their own names.
question_bank: scoring/2027/templates/ASICS_2027_UPD_Scoring_Workbook_v2.xlsx
question_bank_sheet: "UPD Questions_290926 "
question_columns:
  City-Systems Pillar: ASICS 2027_Report_Q No
  Sl. No.: S_No
  Tag: MQ_SQ
  Score / Max Score: Max Score
  Assessment Level: Assessment level
  Evidence / Source Requirement: Notes for scorers
# This category's folder inside outputs/: outputs/ULG/cities/<City>/
outputs: ULG
scoring_workbook: scoring/2027/templates/ASICS_2027_UPD_Scoring_Workbook_v2.xlsx
shared_rules: shared-rules-city
steps:
  1:
    profile: city-profiler
    sources: city-citation-builder
    assess: source-assessor
  2:
    answer: city-answer-writer
  3:
    score: question-scorer
---
The urban local government (ULG). Each ULG question is answered once per city, in the context of
its state. There are no agencies to discover: Step 1 profiles the city government (its Act and
official website) and builds the Citation Sheet (state Acts and rules, master plans,
notifications); Step 2 answers the ULG questions; Step 3 scores them in the expert team's scoring
workbook, one row per city. Today the ULG questions are the UPD (Urban Planning & Design) section;
the SC and DPG sections will be added.
