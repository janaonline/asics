---
name: question-bank-reviewer
title: Question bank reviewer
step: 0
prompt: bank-review
skills: [scoring-methodology]
tools: {}
max_tool_calls: 0
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: high
---
Optional. Reviews the question bank for problems that would make answers unreliable: scoring
scales above the maximum score, assessment levels that don't match the question, MQ totals
that don't add up, unclear applicability.

**Used in:** initial checks, only when asked for (`--llm-bank-review`).
