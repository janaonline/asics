---
name: website-profiler
title: Website profiler
step: 1
prompt: parastatal-profile
skills: [government-websites, india-code-and-acts]
tools:
  web_search: {max_uses: 8}
  web_fetch: {max_uses: 8}
max_tool_calls: 0
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: high
---
For one parastatal: finds the Act that created it, whether it is still active, whether it
has a chief executive and an annual budget, and every candidate official website. It also
fetches government pages that link to the agency, which the website trust check uses.

Each candidate website is then scored in code (see the Website Check column): government
address, links from government websites, government email, NIC hosting, RTI details, social
media accounts linked from government pages, and its name in the address or title.

**Used in:** Step 1, once per parastatal, in parallel.
