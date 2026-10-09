TASK: parastatal_profile

Research one parastatal agency and establish, from official sources fetched this session:
- the legal form (board / corporation / company / authority) and the provision it is
  constituted under;
- its LEGAL INSTRUMENT STACK, layer by layer (located or not located):
    1. parent Act - prefer the current consolidated/amended text; say which version;
    2. Rules made under the parent Act or under the law it is constituted under;
    3. the agency's own Regulations / bye-laws;
    4. constitution and amendment notifications, and GOs (including any recent restructuring
       of the city government);
    5. cross-cutting state laws that name the agency or its services in a schedule
       (service guarantee, RTI rules, procurement transparency);
- whether it is currently active, or has been renamed, merged or replaced;
- the EXECUTIVE AUTHORITY, identified by function, not by title: the post that exercises the
  executive powers under the Act/Rules (in some boards a whole-time Chairman is the executive
  head; in others an MD, Commissioner or CEO). Record: post title; whole-time or part-time;
  whether the same person also chairs the board; the section/rule. If ambiguous, say so;
- whether it publishes an annual budget;
- its official website.

Do not answer or score any ASICS question, and do not judge whether a provision earns credit.
Recording where a provision is (section number, what it covers) is fine.

Finding the official website - research this properly:
1. Search for the agency's website. List every plausible candidate website you find.
2. Search the state government portal and the state urban development department
   (gov.in / nic.in sites) for pages that list or link to this agency, and FETCH at least
   one or two such official pages with web_fetch. These pages are used to check which
   candidate website the government itself links to.
3. If there is no gov.in / nic.in website, still list the best non-government candidates
   (e.g. .org, .in, .com domains). Each candidate is rated automatically on: government
   domain, links from government websites, government email addresses, NIC hosting, RTI
   details, and linked social media accounts. A government page linking to it is the
   strongest proof, so try hard to fetch one.
Never list Wikipedia, directories or social media pages as the website.

"has_chief_executive" is true only if an executive authority post is identified as above;
null if ambiguous.

JSON keys:
  "governing_act": string or null ("<Act, year (Act No.)>; form=<...>; constituted under <section>;
     text version=<...>", with "[unverified]" for any part not seen in a fetched official text),
  "current_status": string (e.g. "Active", "Renamed to X in 2024", "Current status unclear"),
  "has_chief_executive": boolean or null,
  "has_annual_budget": boolean or null,
  "candidate_websites": array of exact, tool-returned URLs, most likely first,
  "government_pages_checked": array of exact URLs of official pages you fetched,
  "notes": string, these segments separated by " | " (write "none" where empty):
     "INSTRUMENTS: Act=<located/not>; Rules=<name or not located>; Regs=<...>;
      Notifications=<...>; CrossLaws=<...>"
     "EXEC: <post; whole-time?; also chairs board?; basis section/rule>"
     "DOMAINS: <official domain(s) + proof>"
     "CONFIRM: <anything a human should check>"
