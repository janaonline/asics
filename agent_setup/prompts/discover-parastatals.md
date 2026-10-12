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

# FOR EACH CATEGORY, SAY WHO DELIVERS THE FUNCTION
For each of the 3 categories, record which body actually delivers it in this city. If the ULG
itself delivers it, or the former parastatal has been merged into the ULG by law or GO, write
"No parastatal - function delivered by ULG" with the evidence in "notes". This is a valid
outcome, not a gap.

# HOW TO RESEARCH
Search the state's urban development department, the state government portal, the state
legislation/gazette portal, the city government's website, and official Acts. Follow the
source rules: only `.gov.in` / `.nic.in` or the agency's own proven official domain count as
evidence. Use the state named in the task input. If the city notes list agencies to screen,
screen every one of them (they are NOT pre-approved: each must pass the tests), and also look
for any other agency doing planning, water/sewerage or public transport for this city.
Different cities organise these functions differently: never assume an agency type exists in
this city because it exists in another. Parastatals listed by the research team are added separately; you do not need to
repeat them, but do apply the tests to them if you find evidence.

# WHAT TO LIST
Every agency you list is researched in full (a long, costly run), so list only what you can
defend. When in doubt, leave it out of "parastatals" and name it in "notes": the team adds it
to the city register if they want it.
- In "parastatals": ONLY agencies that pass ALL of E1-E6 on evidence you fetched in this task.
  "why_included" must name the evidence for E1 (primary statutory function) and E5
  (constituted and functioning today).
- Agencies named in the city notes are candidates to check, not a list to copy. An agency
  is never listed just because the notes name it.
- In "notes", never in "parastatals":
  - agencies that fail any test, with the test, e.g. "<agency>: Not eligible - E4 power
    utility";
  - agencies where a test cannot be decided, e.g. "<agency>: NEEDS REVIEW (E1) - only
    coordinates/regulates, does not deliver the service";
  - state departments and directorates (E3), even if they plan or run a service;
  - bodies that only coordinate, regulate, fund or advise (E1), e.g. a unified transport
    authority, a regional planning board that does not itself prepare the city's plans;
  - bodies whose Act is passed but which are not shown to be constituted and functioning (E5);
  - companies that build infrastructure but do not operate a public service in the city.
- One body per function where possible: if two bodies seem to deliver the same function for
  the same area, list the one whose Act gives it the delivery role, and name the other in
  "notes" with the reason.
- Metro rail: classify as "transport_corporation" only if it operates public passenger
  transport, and add "NEEDS TEAM CONFIRMATION: legal form <company/corporation/other>" to
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
     "why_included": one or two sentences: category, what it does in this city, E1-E6
        result, and the evidence (or the NEEDS REVIEW reason),
     "evidence_urls": array of exact, tool-returned URLs supporting its inclusion
  "notes": string with three parts, separated by " | ":
     "COVERAGE: <category> -> <body, or 'No parastatal - function delivered by ULG'> ..."
     "NOT ELIGIBLE: <agency - failed test> ..."
     "UNCERTAIN: <recent mergers, renamings, conflicting dates, anything to confirm>"
