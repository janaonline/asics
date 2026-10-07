---
name: parastatal-discovery
title: Parastatal discovery
step: 1
prompt: discover-parastatals
skills: [government-websites]
tools:
  web_search: {max_uses: 8}
  web_fetch: {max_uses: 8}
max_tool_calls: 0
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: high
---
Finds the parastatal agencies that serve a city: water and sewerage boards, transport
corporations, development authorities and others (metro rail, housing, slum boards…).

It searches the state government portal, the urban development department, the city
government's website and official Acts. Parastatals listed by the research team in the city
register are always included; the agent adds any others it finds, with the evidence.

**Used in:** Step 1, once per city. **Output:** the list shown on the review screen and in the
Sources workbook's Parastatals sheet.
