---
name: citation-builder
title: Citation builder
step: 1
prompt: find-sources
skills: [government-websites, india-code-and-acts]
tools:
  # Only allowed domains; the code adds the agency's own official domain for each call.
  # Links are re-checked by code afterwards (the Citation Sheet's accessibility test).
  web_search: {max_uses: 5, allowed_domains: [gov.in, nic.in, prsindia.org]}
  web_fetch: {max_uses: 5, allowed_domains: [gov.in, nic.in, prsindia.org], max_content_tokens: 10000}
max_tool_calls: 0
effort: medium
model: claude-sonnet-5-5   # Sonnet 5.5 is the ceiling (also allowed: claude-sonnet-5, claude-haiku-5-5)
---
Builds the Citation Sheet for one parastatal: the official sources needed to answer the
questions that apply to it (Acts, budgets, accounts, annual reports, plans, minutes, charters,
RTI and tender pages…).

It searches twice: first for all the questions, then a targeted search for any question that
still has no verified source. Every link it returns is checked by the source assessor and the
human-accessibility test before it reaches the Citation Sheet.

**Used in:** Step 1, once per parastatal, in parallel.
