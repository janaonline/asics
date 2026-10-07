---
name: citation-builder
title: Citation builder
step: 1
prompt: find-sources
skills: [government-websites, india-code-and-acts]
tools:
  web_search: {max_uses: 8, blocked_domains: [wikipedia.org, justdial.com, indiamart.com]}
  web_fetch: {max_uses: 8}
  check_link: {}
max_tool_calls: 20
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: high
---
Builds the Citation Sheet for one parastatal: the official sources needed to answer the
questions that apply to it (Acts, budgets, accounts, annual reports, plans, minutes, charters,
RTI and tender pages…).

It searches twice: first for all the questions, then a targeted search for any question that
still has no verified source. Every link it returns is checked by the source assessor and the
human-accessibility test before it reaches the Citation Sheet.

**Used in:** Step 1, once per parastatal, in parallel.
