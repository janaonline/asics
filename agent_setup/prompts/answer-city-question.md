TASK: answer_question

Answer one ASICS question for one city using ONLY the Citation Sheet sources provided.
Each source begins with "=== CITATION <ID>: <title> ===". You must not use any other source
or your own knowledge, and must not look anything up. An honest blank beats a plausible fill.

You are shown the most relevant excerpts of each citation. If they don't contain the
decisive passage, use read_citation (more of one citation, by Citation ID) or
search_citation_sheet (search all of them). These tools only reach the Citation Sheet sources
you were given; there is no web access. Use lookup_question if the question depends on another
question.

Known failure modes from the first AI-vs-human audit - guard against these first: answering a
narrower question than the one asked; misreading institutional relationships; stopping at the
parent Act and missing the Rules.

Steps:
1. BRIEF (internal): TEST = what exactly the question tests, naming any relationship or
   comparison (e.g. "the city government's planning role RELATIVE TO the state's"); INSTITUTIONS = every body
   the answer must examine; DECIDING EVIDENCE = the instruments/records that decide it (the
   full stack for "law" questions); TRAP = the nearest narrower question you must NOT answer
   instead.
2. EVIDENCE RULES:
   - City match: evidence must be about THIS city, or the law of THIS city's state. Do not use
     a source merely because it is about the right state; another city's plan is not evidence.
   - Level match: Law/Policy and Institutional Design -> law, rules, binding instruments.
     Implementation -> dated practice evidence. A mandate never proves practice; practice
     never proves a mandate.
   - Period: state the FY/date/version. Current-period question with only older evidence ->
     "partial", no score.
   - "The law" = the whole stack. For "law", "legal framework" or "mandated" questions, say
     what each layer says (e.g. "Act: silent; Rules r.3: fixed 3-year term"), and never
     conclude from the parent Act alone. If the Rules layer is not in the Citation Sheet,
     say so in LIMITS.
   - Relationship questions (who prepares or approves a plan, "in coordination with",
     "consistency with", state vs city roles): read EVERY body's instruments - the Municipal
     Act, the Town and Country Planning Act, any development authority / metropolitan
     planning Act. Name the body that actually prepares or approves, for each plan type.
   - Several provisions -> list each mechanism with its legal strength (approval/concurrence
     > mandatory consultation with response > mandatory consultation > advisory body >
     discretionary "may") and the scope it covers (which plans, areas, decisions).
   - No overclaim: "may" is not "shall"; advisory is not approval; a public notice to all
     citizens is not consultation with the city government; a related figure is not the requested figure.
   - A rubric 0 needs AFFIRMATIVE ABSENCE: every relevant layer was in the Citation Sheet and
     read, no provision was found, and you list what you checked. Otherwise it is "not found",
     never 0.
3. SCORE only if: the answer is sufficient, every rubric component is determined, the
   FIT CHECK below passes, and no CONFIRM condition blocks it. Assign the HIGHEST band in the
   Detailed Methodology whose conditions are ALL met. Never create or interpolate bands.
   Otherwise "proposed_score" = null and explain in notes ("SCORE-BLANK: <reason>").
4. Quote the decisive passage verbatim in "evidence_excerpt" (copied exactly from the
   source text, 1-3 sentences). The quote is checked against the source text in code.
5. FIT CHECK before replying: (a) does the answer respond to the TEST, not the TRAP? (b) are
   all INSTITUTIONS addressed? (c) for "law" questions, were the Rules and other layers
   checked? (d) is the conclusion no stronger than the weakest evidence? Any "no" -> fix it,
   or downgrade to "partial" with a CONFIRM note.
6. If the sources don't answer the question, say what kind of document would (e.g. "the
   notified master plan and its gazette notification"), without URLs.

"sufficiency":
  "sufficient"   - the evidence answers the question;
  "partial"      - it answers part of the question / rubric;
  "insufficient" - no source answers it, or the evidence is outdated, too general or only metadata.

CLASS (where the answer lives) and CONFIDENCE (evidence quality), allowed combinations:
  A1 = one explicit primary provision/record answers it directly -> High (Medium if any
       interpretation).
  A2 = needs 2+ instruments read together, a relationship/overlap judgement, a calculation,
       or PRS-only text -> Medium at most. Relationship questions are A2 unless one provision
       states the relationship explicitly. A2 is never High.
  R  = government holds it but hasn't published -> Low, no score; add "RTI-TARGET: <authority
       or PIO> - <information, period>".
  P  = paywalled/licensed -> Low, no score.
  M  = needs field/agency confirmation -> Low, no score.
  Needs review = the answer depends on an institutional or methodological ambiguity -> Low,
       no score, with a CONFIRM item.

JSON keys:
  "sufficiency": "sufficient" | "partial" | "insufficient",
  "answer": string in this exact format:
     "ANSWER: <direct answer to the TEST> | EVIDENCE: <each instrument checked, with pinpoint
     and short excerpt; for relationship questions, both sides> | CAVEATS: <exceptions,
     partial-scope provisions, conflicts, transitional gaps, or none> | PERIOD: <FY/as-of/
     version> | LIMITS: <evidence gaps, or none>",
  "proposed_score": number or null,
  "citation_id": string (the CITATION ID used, exactly as given; empty if none),
  "citation": string (the section, page or part of that source used),
  "evidence_excerpt": string,
  "missing_evidence": string (only if not sufficient: what kind of source would answer it),
  "notes": string starting with "CLASS: <A1|A2|R|P|M|Needs review>; CONFIDENCE: <High|Medium|
     Low>; BAND: <rubric band matched, short form; for component rubrics list each component
     with ? for undetermined>", then only the prefixes that apply, in this order:
     "CONFIRM:" "SCORE-BLANK:" "ALSO: <other Citation IDs used>" "RTI-TARGET:"
     "SCALE-MISMATCH" "Reviewer to capture a dated screenshot per QB evidence requirement"
