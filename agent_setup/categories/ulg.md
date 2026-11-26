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
# The staged fetch for a link the plain check cannot open: retries and the http/https/www forms, then a
# headless Chromium render (JavaScript pages, certificate errors on official hosts), then the Wayback
# Machine for a 404, a 5xx or a site that cannot be reached. Every copy is marked in the Citation Sheet's
# Copy Type column. off = the plain check only.
staged_fetch: on
# An archived copy older than this many days is marked "stale archive" and is not used (Human
# Verification Required). An archived copy of any age may support a positive finding but never a zero, a
# required source or a complete crawl.
archive_max_age_days: 365
# A link that failed every stage is not tried again for this many hours (0 = always try again).
failure_cache_hours: 24
# Time cap, in minutes, for the retry, browser and archive stages in one run; links after it get the
# plain check only and Needs Attention lists them as "not retried this run" (0 = no cap).
fetch_time_cap_minutes: 20
# Shared cache (outputs/_cache): a page opened in one city or step is reused for this many days
# (0 = never reuse). Scan-read documents never expire.
fetch_cache_max_age_days: 30
# Scan reading: the most one run spends (US$) on Claude reading scanned PDFs. Documents are read
# legal texts and required sources first; one that does not fit is skipped whole and Needs Attention
# lists its pages and cost (0 = off).
scan_reading_budget_usd: 3.00
# How long Step 1 waits (minutes) for a scan-reading batch. If it is not finished, the row says "scan
# reading in progress" and the next Step 1 or re-check collects the result.
scan_batch_wait_minutes: 20
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
