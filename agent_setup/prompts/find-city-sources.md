TASK: find_sources

Build the Citation Sheet for one city: the official sources a researcher needs to answer the
listed ASICS questions for this city, in the context of its state. Use web_search and
web_fetch. The questions will later be answered ONLY from the sources you list here, so aim
to cover every question.

Look for, where they exist: the state's Town and Country Planning Act (or Urban Development /
Planning and Development Act) and its rules; the state's Municipal Corporations / Municipalities
Act; Metropolitan Planning Committee or metropolitan authority Acts; the city's current master
plan / development plan and its notification; zonal, local area or ward plans; the state's
building bye-laws or development control regulations; notifications on planning areas and
boundaries; public-consultation notices for plans; the city government's official website and
its planning department pages.

Prefer the official text (state gazette, state law department, India Code, the department's
own site) and the specific document (the Act PDF, the plan notification) over a home page.
Prefer a smaller number of genuinely official, directly useful sources over many
questionable ones. Only include URLs that a tool returned verbatim.
Use check_link on a candidate before listing it: it runs the same human-accessibility test the
Citation Sheet uses, so prefer links that pass and leave out ones that fail.

JSON keys:
  "sources": array of objects with
     "title": string,
     "url": string (exact, tool-returned),
     "source_type": string (e.g. "Act", "Rules", "Master plan", "Notification", "Official website"),
     "useful_for": string (what this source is useful for, specifically),
     "question_ids": array of question IDs it should help answer
  "notes": string (what you could not find, and why)
