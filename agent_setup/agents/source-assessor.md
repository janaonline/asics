---
name: source-assessor
title: Source assessor
step: 1
prompt: assess-source
skills: [india-code-and-acts]
tools: {}
max_tool_calls: 0
effort: medium
# Haiku 5.5 was tried (Oct 2026, 24 Bengaluru sources): it rejected 3 that Sonnet accepts and
# its scores were off by 2+ on 6, so the assessor stays on Sonnet, reading 15,000 characters
# of each page (ASICS_ASSESS_EVIDENCE_CHARS); that matched Sonnet on 60,000 at half the cost.
model: claude-sonnet-5-5   # Sonnet 5.5 is the ceiling (also allowed: claude-sonnet-5, claude-haiku-5-5)
---
Reads the text of one source that has already been opened successfully, and judges whether it
really supports what it is listed for, whether it is current, and its Authority Score.

It sees only the retrieved text, never the open web. Score caps (unverified = 0,
non-government = at most 5) are applied in code afterwards.

**Used in:** Step 1 (and when Step 2 checks sources the team added), once per link.
