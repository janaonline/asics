---
name: city-profiler
title: City government profiler
step: 1
prompt: city-profile
skills: [government-websites, india-code-and-acts]
tools:
  web_search: {max_uses: 8}
  web_fetch: {max_uses: 8}
max_tool_calls: 0
effort: high
---
For verticals that assess the city government itself (e.g. UPD): finds the Act that governs
the city's municipal body, whether it is active under that name, and every candidate official
website. Candidate websites are scored in code by the same website trust check as parastatals.

**Used in:** Step 1, once per city.
