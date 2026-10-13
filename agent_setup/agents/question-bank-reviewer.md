---
name: question-bank-reviewer
title: Question bank reviewer
step: 0
prompt: bank-review
skills: [scoring-methodology]
tools: {}
max_tool_calls: 0
effort: medium
model: claude-sonnet-5-5   # Sonnet 5.5 is the ceiling (also allowed: claude-sonnet-5, claude-haiku-5-5)
---
Optional. Reviews the question bank for problems that would make answers unreliable: scoring
scales above the maximum score, assessment levels that don't match the question, MQ totals
that don't add up, unclear applicability.

**Used in:** initial checks, only when asked for (`--llm-bank-review`).
