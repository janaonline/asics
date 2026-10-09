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
- In "parastatals": agencies that pass E1-E6, and agencies where a test cannot be decided
  from verified evidence. For an undecided agency, start "why_included" with
  "NEEDS REVIEW (E<n>): <what is unclear>" so the team can decide on the review screen.
- Do NOT list agencies that clearly fail E1-E4 or E6. Name each of them in "notes" with the
  failed test, e.g. "<agency>: Not eligible - E4 power utility".
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
