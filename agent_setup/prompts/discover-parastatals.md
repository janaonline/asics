TASK: discover_parastatals

Find the parastatal agencies that serve one Indian city. A parastatal here means a body
created by the state (or central) government — by an Act, order or company registration —
that plans, builds, finances or delivers urban services or infrastructure in the city, and is
separate from the city's own municipal government (ULG).

Look in particular for:
- water supply and sewerage boards;
- city bus / public transport corporations;
- development authorities (urban development / planning authorities, metropolitan region
  development authorities);
- others, e.g. metro rail corporations, housing boards, slum development boards, urban
  infrastructure finance bodies, solid waste or lake/environment authorities.

Research properly: search the state's urban development department, the state government
portal, the city government's website, and official Acts. Include an agency only if an
official or authoritative source shows it currently operates in this city. Do not include the
ULG itself, its departments, or electricity/telecom companies unless they are clearly urban
parastatals in this state.

Classify each one:
  "type": "water_supply_board" | "transport_corporation" | "development_authority" | "other"
and answer, if you can tell from the evidence:
  "revenue_raising"  - does it raise its own revenue (tariffs, fees, fares, taxes)?
  "capex_mandate"    - does it build infrastructure / carry out capital works?

JSON keys:
  "parastatals": array of objects with
     "id": short acronym, e.g. "BWSSB" (letters/digits only),
     "name": full current official name,
     "type": as above,
     "revenue_raising": boolean or null,
     "capex_mandate": boolean or null,
     "why_included": one sentence: what it does in this city, and the evidence,
     "evidence_urls": array of exact, tool-returned URLs supporting its inclusion
  "notes": string (anything uncertain, e.g. agencies recently merged or renamed)
