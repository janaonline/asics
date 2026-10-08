---
name: city-answer-writer
title: City answer writer
step: 2
prompt: answer-city-question
skills: [scoring-methodology, india-code-and-acts]
tools:
  read_citation: {}
  search_citation_sheet: {}
  lookup_question: {}
max_tool_calls: 8
effort: high
---
Answers one question of a city-level vertical (e.g. UPD) for one city, using ONLY the city's
reviewed Citation Sheet. It names the Citation ID it relies on and quotes the passage word for
word; the quote is checked against the saved page in code.

**Used in:** Step 2, once per city and question. No web research.
