# ASICS Bengaluru Phase 2 — FIX HUMAN-ACCESSIBLE CITATIONS + ANSWER QUESTIONS

Use the existing Asics parastatal bengaluru phase2 · XLSX Excel workbook as the base.
Do NOT create a new structure. Keep all existing sheets and columns.

## CRITICAL PROBLEM TO FIX

The previous run incorrectly marked sources such as:

https://www.indiacode.nic.in/handle/123456789/7903?locale=en

as verified and gave them Authority Score 10 because the tool returned metadata.

THIS IS NOT SUFFICIENT.

A URL being fetchable by a research/API/search tool does NOT mean it is human-accessible.

For this task, "verified" means a normal human can open the exact URL and reach useful source content.

## ABSOLUTE URL RULE

1. NEVER invent, construct, edit, shorten, normalize, or modify a URL.
2. NEVER change http → https.
3. NEVER add/remove paths, parameters, locale values, trailing slashes, etc.
4. NEVER use a URL from memory.
5. A URL may be written to Excel ONLY if that EXACT URL was returned verbatim by a tool call in THIS SESSION.
6. The exact URL returned by the tool must be tested.
7. If no retrieved URL passes the human-accessibility test, leave Official URL blank and explain why in Notes.
8. Do NOT treat search snippets, cached pages, metadata, API responses, redirects, or search-result existence as proof of human accessibility.

## HUMAN ACCESSIBILITY TEST

For every Official URL in the Citation sheet:

A source passes only if the exact URL:

- opens successfully;
- returns the actual page/document/source content;
- contains useful information relevant to the source;
- is not merely a search-result snippet;
- is not merely metadata about another page;
- is not only an API/JSON/XML response;
- is not blocked by robots/access restrictions;
- is not dependent on an unavailable internal tool;
- does not require assuming a different URL;
- does not require constructing a new URL from the returned one.

If the exact URL cannot be opened and its actual content inspected, mark:

Accessibility = "Not human-verified"

Verification Status = "Not verified"

Do NOT give it a "Verified" status.

## VERY IMPORTANT: INDIA CODE

Treat India Code separately.

If an India Code URL can only be fetched as metadata/API/search information but cannot be opened as a normal human-accessible page, DO NOT mark it:

- Accessibility = Public
- Verification Status = Verified
- Authority Score = 10

Instead mark it as not human-verified and explain the limitation.

Do not substitute a guessed India Code URL.

If a different exact India Code URL is discovered by a tool and that exact URL is human-accessible, it may be used.

Otherwise, find another official source returned verbatim by a tool, such as an official government department website or official PDF, if it actually supports the required claim.

## AUTHORITY SCORE

Authority Score measures BOTH authority and usable verification.

Use:

10 = official authoritative source AND exact URL is human-accessible and directly verified

8–9 = official government/agency source, human-accessible, but somewhat indirect/general

6–7 = credible government-linked/official supporting source with limitations

4–5 = secondary/indirect source

1–3 = weak/limited source

0 = unusable/unverified

IMPORTANT:
An official domain alone does NOT automatically mean 10.

An official source that cannot be human-accessed must NOT receive 10.

## CITATION SHEET

Review every existing Citation Sheet row.

For each row:

1. Re-test the exact Official URL.
2. Inspect the actual page/document.
3. Confirm that it is useful for the stated "What This Source Is Useful For".
4. Correct Accessibility.
5. Correct Current/Active Status.
6. Correct Verification Status.
7. Correct Authority Score.
8. Add a concise explanation in Notes.

Do not preserve an incorrect Phase 1 verification merely because it already exists in the workbook.

Prefer a smaller number of genuinely verified sources over many questionable URLs.

## SOURCE PRIORITY

Prefer, in this order:

1. Official parastatal website
2. Official Government of Karnataka website
3. Official Government of India website
4. Official legislation / government PDF
5. Official annual report / notification / government publication
6. Other authoritative source only when necessary

Do not use unofficial aggregators as "official" sources.

## PARASTATAL SCORING - BENGALURU

Now answer the questions in the existing:

"Parastatal Scoring - Bengaluru"

sheet.

For EACH question-parastatal row:

1. Identify the parastatal.
2. Identify the Question ID.
3. Read the corresponding Citation Sheet entries for that parastatal.
4. First attempt to answer using the verified Citation Sheet source.
5. Check whether that source actually supports THIS SPECIFIC QUESTION.
6. Do not use a citation merely because it belongs to the correct parastatal.

## IF CITATION SHEET SOURCE IS INSUFFICIENT

If the Citation Sheet source:

- does not answer the question;
- is outdated;
- is inaccessible;
- is only metadata;
- is too general;
- or does not provide sufficient evidence,

then research an external source.

But the external source must follow the SAME URL rules.

The exact external URL must be returned verbatim by a tool call in this session.

Never construct the URL.

## EXTERNAL SOURCE EXPLANATION

Whenever an external source is used instead of the Citation Sheet source, write a clear explanation in Notes:

"External source used because the Citation Sheet source did not provide sufficient evidence for this specific question. [Brief reason]."

Example:

"External source used because the Citation Sheet India Code link was not human-accessible and therefore could not be independently verified."

Also provide the exact human-readable URL in the Citation field.

## ANSWER QUALITY

Do not infer an answer merely from:

- the existence of a parastatal;
- its statutory mandate;
- a generic website description;
- metadata;
- a search snippet;
- assumptions about what the organisation normally does.

The evidence must support the actual question.

If evidence is insufficient, say so.

## STATUS

Populate Status for every question.

Use clear values such as:

- Answered — Verified Source
- Answered — External Source
- Partially Answered
- Insufficient Evidence
- Human Verification Required

Do not leave Status blank.

## NOTES

Every question must have useful Notes.

Notes should explain:

- what evidence was used;
- whether Citation Sheet or external source was used;
- any limitation;
- why an external source was necessary;
- whether human verification is still required.

Do not write generic notes such as "Source checked."

## CITATION

For every answered question:

- Citation must identify the source used.
- Citation URL must be the exact URL returned by the tool.
- Never invent or modify URLs.
- If no verified human-accessible URL supports the answer, clearly state that in the Citation/Notes rather than fabricating a link.

## IMPORTANT DISTINCTION

Use this logic:

TOOL CAN FETCH URL
        ↓
NOT ENOUGH
        ↓
CAN A HUMAN OPEN THE EXACT URL?
        ↓
YES → inspect actual content → verified
NO  → NOT HUMAN-VERIFIED

Never use:

TOOL CAN FETCH METADATA
        ↓
THEREFORE VERIFIED

That logic caused the previous incorrect India Code result.

## PRESERVE WORKBOOK

Keep:

- all existing sheets;
- existing sheet names;
- existing columns;
- existing formatting where possible;
- existing question order;
- existing parastatal order.

Do not delete useful existing data.

Correct inaccurate Phase 1 data where necessary.

Do not calculate scores unless the workbook methodology explicitly requires it.

## FINAL QA

Before saving:

1. Check every Official URL in Citation Sheet.
2. Confirm it was returned verbatim by a tool in this session.
3. Confirm exact URL was human-accessibility tested.
4. Remove/flag URLs that only returned metadata or snippets.
5. Check India Code specifically.
6. Check every question has an answer or explicit insufficient-evidence status.
7. Check every question has Status.
8. Check every question has Notes.
9. Check external-source usage is explicitly explained.
10. Ensure no URL was invented or modified.

Save the completed workbook as:

ASICS_Parastatal_Bengaluru_Phase2.xlsx

Return the Excel file only after these checks are complete.
