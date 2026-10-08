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
   is missing. A person will score it. Never guess.
5. "citation_id" is the one Citation ID your inputs rest on. "quote" is the decisive passage
   copied word for word from that citation (1-3 sentences). Both are checked in code: an
   input with a wrong ID or a quote that isn't in the source is discarded.

JSON keys:
  "inputs": {"<column name exactly as given>": "<value>" or number or ""},
  "citation_id": string,
  "quote": string,
  "chapter": string, "provision": string, "clause": string (where in the document, if known),
  "comments": string (why these inputs; anything a person should check),
  "confidence": "high" | "medium" | "low"
