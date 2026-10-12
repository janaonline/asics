TASK: discover_parastatals

Find the parastatal agencies that serve one Indian city, for the ASICS parastatal assessment.

# SCOPE: only 3 categories
A parastatal here is a body created by the state (or central) government, by statute, GO or
government-owned incorporation, that is separate from the city's own government (ULG) and
whose PRIMARY statutory function is one of:
  1. Development / planning authorities (planning, land development);
  2. Water supply and sewerage utilities;
  3. Public transport agencies (operating, or building and operating, public passenger
     transport).
EXCLUDED by the approach note, even if they work in the city: housing boards, roads agencies,
power utilities (e.g. electricity supply companies), Smart City SPVs, environment bodies,
state line departments and directorates. The ULG itself, its departments, and any body merged
into the ULG are not parastatals.

# ELIGIBILITY TESTS (apply in order, from evidence you fetched, never from a name or memory)
  E1 Category: primary statutory function is in one of the 3 categories. If it only
     regulates, coordinates or funds -> needs review.
  E2 Not the ULG itself, not a ULG department, not merged into the ULG.
  E3 Not a state line department or directorate.
  E4 Not in the exclusion list above.
  E5 Constituted by statute, GO or government-owned incorporation, AND constituted and
     functioning today. An Act passed but the body not constituted -> needs review.
  E6 Its jurisdiction covers all or a substantial part of the city's ULG area as currently
     notified.

A public transport body that builds AND is mandated to operate the service (e.g. a metro
company whose line is under construction) meets category 3. List it as eligible if E1-E6
otherwise pass, and add 'PRE-OPERATIONAL: <status, e.g. under construction / trial runs>' to
why_included.

# FOR EACH CATEGORY, SAY WHO DELIVERS THE FUNCTION
For each of the 3 categories, record which body actually delivers it in this city. If the ULG
itself delivers it, or the former parastatal has been merged into the ULG by law or GO, write
"No parastatal - function delivered by ULG" with the evidence in "notes". This is a valid
outcome, not a gap.

# HOW TO RESEARCH
Search the state's urban development department, the state government portal, the state
legislation/gazette portal, the city government's website, and official Acts. Prefer `.gov.in` /
`.nic.in` pages. For deciding eligibility you may use the agency's own website even if its
domain is not proven official. If at least one gov.in / nic.in page fetched in this task names
the agency (a GO, notice, tender, annual report, department page), and the own site states its
constitution, the agency can be eligible; add 'DOMAIN: <own domain> - proof pending, checked
in the profile step' to why_included. If the only evidence is the unproven own site, list it
as needs_review with 'NEEDS REVIEW (domain proof pending): <what the site says, e.g.
constituted under s.X of <Act>>'. Blocked sites (Wikipedia, Indian Kanoon, news, blogs) stay
leads only, even for exclusions: find the official copy of the same instrument. Use the state
named in the task input.
Read the scope decisions note from the research team and follow it when it covers a case. For
a company owned by the city government (E2), use needs_review unless that note says otherwise.
If the city notes list agencies to screen, screen every one of them (they are NOT
pre-approved: each must pass the tests), and also look for any other agency doing planning,
water/sewerage or public transport for this city.
Different cities organise these functions differently: never assume an agency type exists in
this city because it exists in another. Parastatals listed by the research team are added
separately; you do not need to repeat them, but do apply the tests to them if you find evidence.
Work breadth-first. First identify a candidate body (or 'delivered by the ULG') for EACH of the
3 categories, using searches and at most 2 page fetches per candidate. Only then use the
remaining budget to check E1-E6 in more depth. If you run out, list the candidates you have as
needs_review rather than leaving a category NOT DETERMINED with nothing listed.
Search the city government's own gov.in site and state department sites for documents that
name the candidate (notices, tenders, EOIs, recruitment notices, annual reports): these often
prove a body exists and what it does when its own site blocks automated tools.

# WHAT TO LIST
Every agency you list as "eligible" is researched in full (a long, costly run). Agencies you
list as "needs_review" are shown to the research team, unticked, and researched only if they
tick them. Each agency ends in one of three places:
- "parastatals" with "status": "eligible": passes ALL of E1-E6 on evidence you fetched in this
  task. "why_included" must name the evidence for E1 (primary statutory function) and E5
  (constituted and functioning today).
- "parastatals" with "status": "needs_review": a test cannot be decided from the evidence you
  fetched, e.g. E1 it may only coordinate or regulate rather than deliver; E2 a company that may
  be owned by the city government; E5 constituted but whether it functions is unclear; E6
  jurisdiction unclear; or its website was blocked so the evidence could not be fetched.
  "why_included" must start with "NEEDS REVIEW (E<n>): <reason>".
- "notes" only, never in "parastatals": agencies that clearly fail a test, with the test, e.g.
  "<agency>: Not eligible - E4 power utility":
  - state departments and directorates (E3), even if they plan or run a service;
  - excluded types (E4): power utilities, housing boards, roads agencies, Smart City SPVs,
    environment bodies;
  - agencies clearly outside the city (E6);
  - companies that only BUILD infrastructure and hand it over to another operator.
When in doubt, list it as needs_review.
- Agencies named in the city notes are candidates to check, not a list to copy. An agency
  is never listed as "eligible" just because the notes name it.
- One body per function where possible: if two bodies seem to deliver the same function for
  the same area, list as "eligible" the one whose Act gives it the delivery role, and name the
  other in "notes" with the reason (or list it as needs_review if you cannot tell which it is).
- Metro rail: classify as "transport_corporation" if it operates public passenger transport,
  or is mandated to build and operate it (add the PRE-OPERATIONAL flag if not yet open), and add "NEEDS TEAM CONFIRMATION: legal form <company/corporation/other>" to
  "why_included".

Classify each listed agency:
  "type": "water_supply_board" | "transport_corporation" | "development_authority" | "other"
and answer, only if the evidence shows it:
  "revenue_raising"  - does it raise its own revenue (tariffs, fees, fares, taxes)?
  "capex_mandate"    - does it build infrastructure / carry out capital works?

JSON keys:
  "parastatals": array of objects with
     "id": the official acronym, uppercase letters/digits only, e.g. "BWSSB",
     "name": full current official name,
     "type": as above,
     "revenue_raising": boolean or null,
     "capex_mandate": boolean or null,
     "status": "eligible" | "needs_review",
     "why_included": one or two sentences: category, what it does in this city, E1-E6
        result, and the evidence (for needs_review: starts "NEEDS REVIEW (E<n>): <reason>"; add
        "PRE-OPERATIONAL: ..." or "DOMAIN: ..." where those rules above apply),
     "evidence_urls": array of exact, tool-returned URLs supporting its inclusion
  "notes": string with three parts, separated by " | ":
     "COVERAGE: <category> -> <body, or 'No parastatal - function delivered by ULG'> ..."
     "NOT ELIGIBLE: <agency - failed test> (clear fails only; undecided ones are listed as needs_review)"
     "UNCERTAIN: <recent mergers, renamings, conflicting dates, anything to confirm>"
