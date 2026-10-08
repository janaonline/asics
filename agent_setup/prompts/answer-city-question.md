TASK: answer_question

Answer one ASICS question for one city using ONLY the Citation Sheet sources provided.
Each source begins with "=== CITATION <ID>: <title> ===". You must not use any other source
or your own knowledge, and must not look anything up.

You are shown the most relevant excerpts of each citation. If they don't contain the
decisive passage, use read_citation (more of one citation, by Citation ID) or
search_citation_sheet (search all of them). These tools only reach the Citation Sheet sources
you were given; there is no web access. Use lookup_question if the question depends on another
question.

Steps:
1. Check whether a source actually supports THIS SPECIFIC QUESTION. Do not use a source
   merely because it is about the right city or state.
2. Apply the Detailed Methodology and propose a score within 0 and the maximum score,
   only when the methodology gives a scoring rule and the evidence supports it.
3. Quote the decisive passage verbatim in "evidence_excerpt" (copied exactly from the
   source text, 1-3 sentences). The quote is checked against the source text.
4. If the sources don't answer the question, say what kind of document would (e.g. "the
   Board's latest annual report, which lists sanctioned and working staff"), without URLs.

"sufficiency" is:
  "sufficient"   - the evidence answers the question;
  "partial"      - it answers part of the question;
  "insufficient" - no source answers it, or the evidence is outdated, too general or only metadata.

JSON keys:
  "sufficiency": "sufficient" | "partial" | "insufficient",
  "answer": string,
  "proposed_score": number or null,
  "citation_id": string (the CITATION ID used, exactly as given; empty if none),
  "citation": string (the section, page or part of that source used),
  "evidence_excerpt": string,
  "missing_evidence": string (only if not sufficient: what kind of source would answer it),
  "notes": string (what evidence was used, any limitation, whether a human should verify)
