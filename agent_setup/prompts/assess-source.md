TASK: assess_source

You are given one candidate source and the readable text that was retrieved by opening its
exact URL. Judge the source only on this text.

Authority Score measures BOTH authority and usable verification:
  10  = official authoritative source, and the content directly supports the stated use
  8-9 = official government/agency source, but somewhat indirect or general
  6-7 = credible government-linked/official supporting source with limitations
  4-5 = secondary or indirect source
  1-3 = weak or limited source
  0   = unusable
An official domain alone does NOT mean 10.

JSON keys:
  "useful": boolean (does the text actually support "What This Source Is Useful For"?),
  "useful_for": string (corrected, specific description of what it supports),
  "current_status": string ("Current", "Outdated (year)", "Superseded by ...", "Unknown"),
  "authority_score": number 0-10,
  "notes": string (concise: what the page contains and any limitation)
