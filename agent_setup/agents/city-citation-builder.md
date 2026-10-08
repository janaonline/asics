---
name: city-citation-builder
title: City citation builder
step: 1
prompt: find-city-sources
skills: [government-websites, india-code-and-acts]
tools:
  web_search: {max_uses: 8, blocked_domains: [wikipedia.org, justdial.com, indiamart.com]}
  web_fetch: {max_uses: 8}
  check_link: {}
max_tool_calls: 20
effort: high
---
Builds the Citation Sheet for one city in a city-level vertical (e.g. UPD): the state's Acts
and rules (e.g. its Town and Country Planning Act), the city's plans, notifications and
official pages. Every link is checked by the source assessor and the human-accessibility test.

**Used in:** Step 1, once per city.
