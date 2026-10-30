---
name: city-citation-builder
title: City citation builder
step: 1
prompt: find-city-sources
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
Builds the Citation Sheet for one city in the ULG category: the state's Acts
and rules (e.g. its Town and Country Planning Act), the city's plans, notifications and
official pages. Every link is checked by the source assessor and the human-accessibility test.

**Used in:** Step 1, once per city.
