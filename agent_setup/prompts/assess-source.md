TASK: assess_source

You are given one candidate source and the readable text that was retrieved by opening its
exact URL. Judge the source only on this text. Do not answer or score any ASICS question. The source
must be about the city and state named in the input: a document about another city or
another state's law is not useful for this one.

Authority Score (for a source whose text you can read):
  10  = Gazette / GO / notification / official full text of an Act or Rules on a gov.in /
        nic.in domain, directly establishing the stated use
  9   = an official site page of the body being assessed (parastatal or city government),
        or a government portal / CAG report, directly establishing it
  8   = a 9-10 source that supports the stated use only generally or indirectly
  7   = official but legacy/secondary official domain, or visibly outdated content
  6   = PRS Legislative Research republished legal text (secondary)
  1-5 = weak, indirect or barely relevant
  0   = unusable, or the text does not support the stated use
An official domain alone does NOT mean 10. India Code text that shows only the Act's
title/number/date (metadata) is at most 1. (Caps for unverified and non-government sources
are applied in code afterwards.)

"current_status" format: "<Current | Historical | Transitional | Current status unclear>;
era=<era tag from the city notes, or n/a>; period=<FY/date/version shown | not stated>".
A legacy-era governance document is never "Current".

JSON keys:
  "useful": boolean (does the text actually support "What This Source Is Useful For"?),
  "useful_for": string (corrected, specific: "[TAG] <content + section/page + period>"),
  "current_status": string (format above),
  "authority_score": number 0-10,
  "notes": string (concise: what the page contains, the text version, any limitation)
