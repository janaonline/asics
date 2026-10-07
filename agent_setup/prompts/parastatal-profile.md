TASK: parastatal_profile

Research one parastatal agency and establish:
- the Act, statute or government order that establishes it, and its current name;
- whether it is currently active, or has been renamed, merged or replaced;
- whether it has a chief executive post (e.g. Managing Director, Commissioner, Chairperson
  with executive powers) and publishes an annual budget;
- its official website.

Finding the official website — research this properly:
1. Search for the agency's website. List every plausible candidate website you find.
2. Search the state government portal and the state urban development department
   (gov.in / nic.in sites) for pages that list or link to this agency, and FETCH at least
   one or two such official pages with web_fetch. These pages are used to check which
   candidate website the government itself links to.
3. If there is no gov.in / nic.in website, still list the best non-government candidates
   (e.g. .org or .in domains). Each candidate is rated automatically on: government domain,
   links from government websites, government email addresses, NIC hosting, RTI details,
   and linked social media accounts.
Never list Wikipedia, directories or social media pages as the website.

JSON keys:
  "governing_act": string or null (name and year of the Act / order),
  "current_status": string (e.g. "Active", "Renamed to X in 2024"),
  "has_chief_executive": boolean or null,
  "has_annual_budget": boolean or null,
  "candidate_websites": array of exact, tool-returned URLs, most likely first,
  "government_pages_checked": array of exact URLs of official pages you fetched,
  "notes": string (the evidence for each point, and anything a human should check)
