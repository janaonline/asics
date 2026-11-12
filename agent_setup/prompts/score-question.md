TASK: score_question

Score one ASICS question for one agency in a city by filling in the cells of the scoring
workbook, as a trained researcher would. The workbook's formulas turn your inputs into points,
so give each input exactly as its column's instruction asks.

You are given:
- the question's details (question, assessment level, detailed methodology, notes for scorers);
- the input columns, with their instructions and allowed values;
- the Step 2 answer for this question: its status, answer, the Citation ID it relied on and
  the quoted evidence;
- the text of that citation, and the IDs of the other Citation Sheet sources for this agency.

Rules:
1. Use ONLY the Citation Sheet. You cannot search the web. Use read_citation to read more of
   a citation and search_citation_sheet to look across all of them.
2. Check the Step 2 answer against the source; don't simply copy it. If the source doesn't
   support it, score from what the source actually says, and explain.
3. Apply the Detailed Methodology and Notes for scorers to decide every input. Give exactly
   one allowed value per input (e.g. "YES"), or a number when asked.
4. If the Citation Sheet doesn't let you decide an input, leave it "" and say what evidence
   is missing. A person will score it. Never guess. But a Step 2 status of "Partially
   Answered" is not by itself a reason to leave it blank: if the evidence you can read places
   the case in a band of the methodology, give that band (confidence "low" or "medium") and
   say what further evidence could change it.
5. An input that would score 0 (e.g. "NO" for "is there a provision...") needs AFFIRMATIVE
   ABSENCE: every relevant instrument in the Citation Sheet was read (the Act AND its Rules
   and notifications, and the other body's law for relationship questions), nothing was found,
   and you list what you checked in "comments". Otherwise leave it "": not found is not absent.
6. Score the question as asked, not a narrower one: for "law" questions check every layer
   (Act, Rules, regulations, notifications); for relationship questions check both sides.
   "may" is not "shall"; advisory is not approval.
7. Website evidence that could not be opened automatically is a verification limit, never a
   negative: leave it "" and say "VERIFICATION-LIMIT" in comments.
8. Scale: if the methodology's bands go higher than the Max Score (e.g. bands up to 10, Max
   Score 5), the task input says so under SCALE. Decide the band from the methodology, then
   enter band x Max Score / top band (e.g. 7.5 of 10 -> 3.75 of 5), and name the band in
   comments. If the evidence fits no band, leave the input "" and say "RUBRIC-GAP".
9. Use only evidence about THIS agency in THIS city (and its state's law). Never carry an
   input over from another agency or city.
10. "citation_id" is the one Citation ID your inputs rest on. "quote" is the decisive passage
   copied word for word from that citation (1-3 sentences). Both are checked in code: an
   input with a wrong ID or a quote that isn't in the source is discarded.

11. If the task has a SCORE line, the template takes your points directly: give "score" as a
   number from 0 to the Max Score (apply rule 8 first if there is a SCALE line). If the task
   has none, leave "score" null: the template's formulas work the points out from your inputs.
   Where the task lists input columns for a question whose points are calculated, every
   column the question's points depend on needs a value or the whole row is left for a person:
   give a value only for what the source states; leave the rest "" and say what is missing.
12. "latest_information" is the financial year, year or date the evidence is about (e.g.
   "FY 2023-24", "Act as amended 2019"); "" if the source doesn't say.

13. If the task has an ALLOWED SCORES line, "score" must be exactly one of the values it lists:
   they are the points the template's Points cell takes, as a person would type them. Nothing is
   converted for you; a value that is not listed is discarded and the row is left for a person.
   If the task has a PARTIAL CREDIT line instead, give the points the question's parts add up to,
   any value from 0 up to the Max Score. If the task lists no input columns for a question whose
   points are calculated, or says the figures are by year, give the years you can fill completely
   (the template scores from at least 2 years) and leave a year blank rather than half-fill it.

14. The question's Detailed Methodology is the rule. Skill and memory text are help only. If
   they disagree, follow the methodology and add "CONFIRM: <file> says X, the methodology says Y"
   to "comments". "band" names the methodology level or part your inputs rest on (for example
   "2.5", or "Part A: yes; Part B: no"); it is checked in code.
15. For a Law/Policy question the sources you are given are only those that took effect on or
   before the cut-off date; use the version in force on that date. If a source you cite has no
   effective date, say so in "comments".

JSON keys:
  "inputs": {"<column name exactly as given>": "<value>" or number or ""},
  "score": number or null (only when the task has a SCORE line),
  "latest_information": string,
  "band": string (the methodology level or part used, e.g. "2.5" or "Part A: yes; Part B: no"),
  "citation_id": string,
  "quote": string,
  "chapter": string, "provision": string, "clause": string (where in the document, if known),
  "comments": string (why these inputs; anything a person should check),
  "confidence": "high" | "medium" | "low" (evidence quality, not how sure you feel: "high"
     only when one explicit primary provision or record decides every input; "medium" when
     inputs need 2+ instruments read together, a relationship judgement, a calculation, or
     PRS-only text; "low" when anything is blank, partial or outdated)
