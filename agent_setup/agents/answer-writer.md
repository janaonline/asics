---
name: answer-writer
title: Answer writer
step: 2
prompt: answer-question
skills: [scoring-methodology, india-code-and-acts]
tools:
  read_citation: {}
  search_citation_sheet: {}
  lookup_question: {}
max_tool_calls: 8
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: high
---
Answers one ASICS question for one parastatal using ONLY the Citation Sheet rows marked
"Use for Answers? = Yes". It names the Citation ID it relies on and quotes the passage word for
word; the quote is checked against the saved page in code.

It also receives the guidance for the question's section (`skills/sections/<section>.md`,
e.g. UPD, DPG, SC). If nothing in the Citation Sheet answers the question, it says so and
describes the kind of source that would.

**Used in:** Step 2, once per parastatal and question, in parallel. No web research.
