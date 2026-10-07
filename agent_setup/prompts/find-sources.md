TASK: find_sources

Build the Citation Sheet for one parastatal: the official sources a researcher needs to
answer the listed ASICS questions. Use web_search and web_fetch. The questions will later be
answered ONLY from the sources you list here, so aim to cover every question.

Look for, where they exist: the parastatal's Act and rules; the applicable Town and Country
Planning Act; the official website; the annual budget; audited accounts; the annual report;
governing board meeting minutes; master plans or sectoral plans; the citizen or service
charter; RTI / PIO pages; procurement or tender pages; service-level benchmark reports;
grievance-redressal pages; staffing and organisation information.

Prefer the specific page or document (e.g. the budget PDF) over a site's home page. Prefer a
smaller number of genuinely official, directly useful sources over many questionable ones.
Only include URLs that a tool returned verbatim.
Use check_link on a candidate before listing it: it runs the same human-accessibility test the
Citation Sheet uses, so prefer links that pass and leave out ones that fail.

JSON keys:
  "sources": array of objects with
     "title": string,
     "url": string (exact, tool-returned),
     "source_type": string (e.g. "Act", "Official website", "Budget", "Annual report", "Plan"),
     "useful_for": string (what this source is useful for, specifically),
     "question_ids": array of question IDs it should help answer
  "notes": string (what you could not find, and why)
