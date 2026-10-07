---
name: source-assessor
title: Source assessor
step: 1
prompt: assess-source
skills: [india-code-and-acts]
tools: {}
max_tool_calls: 0
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: medium
---
Reads the text of one source that has already been opened successfully, and judges whether it
really supports what it is listed for, whether it is current, and its Authority Score.

It sees only the retrieved text, never the open web. Score caps (unverified = 0,
non-government = at most 5) are applied in code afterwards.

**Used in:** Step 1 (and when Step 2 checks sources the team added), once per link.
