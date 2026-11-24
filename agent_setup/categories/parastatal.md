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
# on: a score of 0 is allowed only when every source the question requires is in the agency's
# Citation Sheet and was read (data/question_source_requirements.yaml); otherwise the score stays
# blank and the note says "Missing: <source>". Set to off to go back to the earlier behaviour.
required_sources: on
# on: a source a person has verified (Citation Sheet column "Human-Verified?" = Yes) is marked for the
# AI, pinned among the sources it reads, and an answer that rests on it is "Answered — Human-Verified
# Source". The app still opens and saves every such link and the AI still has to quote it word for
# word. Set to off to stop using the mark (the column itself is always kept).
human_verified_sources: on
# Step 1 also opens the menu links of each agency's confirmed official home page, one level deep, up
# to this many pages (0 = off). A crawl counts as complete only when every menu link was captured;
# without a complete crawl no zero is allowed for a "is it on the website?" question.
crawl_max_pages: 15
# strict (the default): any menu link that did not open makes the crawl incomplete, so website
# questions stay blank. lenient: a dead link whose text and address name no topic word (budget,
# report, tender, RTI, charter, board, plan ...) is ignored; a dead link that does stays a problem.
# To switch, change the word, save, and restart the app.
crawl_incomplete_on_dead_link: strict
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
scan_reading_budget_usd: 5.00
# How long Step 1 waits (minutes) for a scan-reading batch. If it is not finished, the row says "scan
# reading in progress" and the next Step 1 or re-check collects the result.
scan_batch_wait_minutes: 20
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
