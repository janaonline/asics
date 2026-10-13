TASK: find_sources

Build the Citation Sheet for one parastatal: the official sources a researcher needs to
answer the listed ASICS questions. Use web_search and web_fetch. The questions will later be
answered ONLY from the sources you list here, so aim to cover every question. Do not answer
or score any question here.

Order of work:
1. Leads from the research team (in the message, if any) FIRST. If a lead is on a blocked
   domain, search for the same instrument on an allowed domain and cite only that copy.
2. Then independent searches.

Your searches and page fetches are limited, so spend them in this order and stop padding:
  1. [ACT] full text on an allowed domain (the state legislation/gazette portal, India Code
     full-text PDF, the agency's own site), then [RULES] and [AMEND].
  2. [ULG-LAW] and [TCP] - most relationship questions (UPD 1-2, DPG 1) cannot be answered
     without them.
  3. [BUDGET], [AR], [ACCOUNTS] - most State Capacities questions need them.
  4. [BOARD-LIST], [EXEC-LAW], [CE-APPT], [ORG], [STAFF-DATA].
  5. Website-feature tags ([WEB], [WEB-FEATURE], [RTI], [GRIEV], [PROCURE], [CHARTER]).
  6. Everything else.
Prefer one document that covers several tags (e.g. an annual report with staffing,
accounts and board) over several narrow pages. A home page alone is weak evidence for any
question: prefer the specific page or PDF.
Try to locate ONE best source per evidence tag. Add a second source for a tag only if the
first did not pass check_link or covers a different period. Never pad the list.

If an official site blocks automated tools (check_link says so), still list the specific
page, AND look for the same document on another allowed host (e.g. the Act on the state
legislation portal or India Code instead of the agency site; an annual report in the state
legislature's papers-laid pages). Never replace it with a blocked mirror (Indian Kanoon,
FAOLEX, Wikipedia, news).

EVIDENCE TAGS (start every "useful_for" with the tag in brackets):
- Identity: [IDENTITY] mandate and functions.
- Legal stack (read the WHOLE stack, never stop at the Act):
  [ACT] parent Act, current text; [AMEND] amendments, incl. recent city-government changes;
  [RULES] rules made under the Act or under the constituting law (tenure, board, procedure,
  budget, accounts); [REGS] the agency's regulations/bye-laws (cadre, recruitment, conduct of
  business); [BOARD-LAW] composition clause; [JURIS] jurisdiction (schedule, notification, map).
- Board and executive: [BOARD-LIST] current board members; [EXEC-LAW] provisions on the
  executive authority's appointment, term, tenure and removal; [CE-APPT] GOs/gazette on
  executive-head appointments and transfers in the last 5 years.
- Website: [WEB] official homepage; [WEB-FEATURE] grievance portal, RTI page, tender page, apps.
- Finance: [BUDGET]; [ACCOUNTS] audited; [AR] annual report (check the agency site AND the
  state legislature's papers-laid pages); [FISCALPLAN] medium/long-term fiscal plan.
- Governance records: [MINUTES] board; [ORG] organisation/staffing; [STAFF-DATA] sanctioned
  vs filled posts, gender.
- Plans and performance: [PLANS]; [SECTORPLAN] water/sewerage master plan or mobility/fleet
  plan; [SLB] service-level reports; [TARIFF] tariff/fare orders.
- Citizen interface: [CHARTER]; [RTI] PIO details; [PROCURE] tenders/awards; [GRIEV];
  [PARTICIPATION] advisory committees, public-consultation notices.
- Oversight: [CAG].
- Shared context (the same document may serve several parastatals):
  [ULG-LAW] the city government's Act - functions schedules, planning-authority status, and
  any power to coordinate, supervise, direct or approve public authorities/parastatals;
  [TCP] the Town and Country Planning Act - plan preparation, notice, objections, membership;
  [CROSSLAW] state laws naming the agency or its services (service guarantee, RTI rules,
  procurement).

"useful_for" format: "[TAG] <specific content + pinpoint (section/rule/page) + period>;
era=<era tag from the city notes, or n/a>". For Acts, Rules and ULG-LAW, list the key section
numbers you located. Vague phrases ("useful for governance") are not allowed. Location notes
only, e.g. "ULG Act s.X gives the ULG a coordination role over public authorities" - never a
verdict such as "therefore functions are not demarcated".

Prefer the specific page or document (e.g. the budget PDF) over a home page. Only include URLs
that a tool returned verbatim, on allowed domains. Use check_link on each candidate before
listing it: it runs the same human-accessibility test the Citation Sheet uses. Prefer links
that pass. If an important source fails check_link because the site blocks automated tools,
you may still list it and say so in "notes" - a person will open it.

JSON keys:
  "sources": array of objects with
     "title": string (the title exactly as shown on the page/document),
     "url": string (exact, tool-returned),
     "source_type": string, one of: "Enabling Act / Legislation", "Amendment Act", "Rules",
        "Regulations / Bye-laws", "Gazette Notification", "Government Order",
        "Official Parastatal Website", "Annual Report", "Budget", "Audited Accounts",
        "Official Plan", "CAG Report", "Legislature Paper", "Government Publication",
        "Government Department Source", "Official Statistics", "Secondary Legal Text (PRS)",
     "useful_for": string (format above),
     "question_ids": array of question IDs it should help answer
  "notes": string: "GAPS: <tags not located, and for RULES the searches tried>" |
     "TEAM-LEAD: <lead> -> <allowed copy found | not found>" | "CHECK: <url that blocked
     automated tools>"
