---
name: question-scorer
title: Question scorer
step: 3
prompt: score-question
skills: [scoring-methodology, india-code-and-acts]
tools:
  read_citation: {}
  search_citation_sheet: {}
max_tool_calls: 8
# model: claude-sonnet-5-5   # optional: a different Claude model for this agent
effort: high
---
Step 3. Scores one question for one agency in a city by filling in the same cells of the
scoring workbook an intern would: the inputs the row above each column asks for (e.g.
YES / NO), plus the provision used and comments. The workbook's own formulas turn the inputs
into points, exactly as for people's scores.

It works only from Step 2: the question's answer and the reviewed Citation Sheet. No web
research. It must name the Citation ID it relies on and quote it word for word; code checks
both, and copies the document name and link from the Citation Sheet itself. If Step 2 found
no evidence, or a check fails, the inputs are left blank for a person.

**Used in:** Step 3, once per question and agency, after Step 2 has answered the city. Its
scores are compared with people's scores (the golden dataset).
