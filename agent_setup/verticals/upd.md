---
name: upd
title: UPD
code: UPD
# What is assessed in each city: the city government itself (its ULG), under its state's laws.
unit: city_government
# The UPD question list is a sheet of the UPD scoring workbook; its columns have their own names.
question_bank: scoring/2027/templates/ASICS_2027_UPD_Scoring_Workbook_v2.xlsx
question_bank_sheet: "UPD Questions_290926 "
question_columns:
  City-Systems Pillar: ASICS 2027_Report_Q No
  Sl. No.: S_No
  Tag: MQ_SQ
  Score / Max Score: Max Score
  Assessment Level: Assessment level
  Evidence / Source Requirement: Notes for scorers
# City folders: outputs/verticals/upd/cities/<City>/
outputs: verticals/upd
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
Urban Planning & Design: the state's town and country planning framework and the city's own
planning, assessed for each city in the context of its state. There are no agencies to
discover: Step 1 profiles the city government (its Act and official website) and builds the
Citation Sheet (state Acts and rules, master plans, notifications); Step 2 answers the UPD
questions; Step 3 scores them in the expert team's UPD scoring workbook, one row per city.
