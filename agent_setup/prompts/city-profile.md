TASK: parastatal_profile

Research one city government (the urban local government, ULG: e.g. a Municipal Corporation)
and establish:
- the Act under which it is constituted (e.g. the state's Municipal Corporations Act), and its
  current name;
- whether it is active under that name, or has been renamed, split or merged (e.g. into a
  new metropolitan authority);
- whether it has a chief executive post (e.g. Municipal Commissioner) and publishes an annual
  budget;
- the bodies that share its planning functions in this city (a development authority, a
  metropolitan planning committee or authority, the state town planning department), and the
  Act each is constituted under - location notes only, no verdicts;
- its official website.

Finding the official website: research this properly.
1. Search for the city government's website. List every plausible candidate website you find.
2. Search the state government portal and the state urban development department
   (gov.in / nic.in sites) for pages that list or link to the city government, and FETCH at
   least one or two such official pages with web_fetch. These pages are used to check which
   candidate website the government itself links to.
3. If there is no gov.in / nic.in website, still list the best candidates. Each candidate is
   rated automatically on: government domain, links from government websites, government
   email addresses, NIC hosting, RTI details, and linked social media accounts.
Never list Wikipedia, directories or social media pages as the website.

JSON keys:
  "governing_act": string or null ("<Act, year>; text version=<as enacted | as amended up
     to <date> | unknown>", with "[unverified]" for any part not seen in a fetched official text),
  "current_status": string (e.g. "Active", "Renamed to X in 2024"),
  "has_chief_executive": boolean or null,
  "has_annual_budget": boolean or null,
  "candidate_websites": array of exact, tool-returned URLs, most likely first,
  "government_pages_checked": array of exact URLs of official pages you fetched,
  "notes": string, segments separated by " | ": "EVIDENCE: <for each point>" |
     "PLANNING BODIES: <body - Act - role, location only>" | "DOMAINS: <official domain(s) +
     proof>" | "CONFIRM: <anything a human should check, e.g. a recent renaming or split>"
