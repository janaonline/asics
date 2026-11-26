# Re-run checklist, version 2 (steps you do on the portal)

Written for the person who runs the portal (`Start ASICS.command`). Nothing here has been run: no model call, no Step 1, 2 or 3, no Re-check links. Costs are estimates **[A]** from the 16 and 17 Nov usage files (Step 1 Bengaluru $3.91, Bhubaneswar $1.97 and $2.15; Step 2 $10.93 and $5.07; Step 3 $1.42 and $0.35). Each run's real cost shows on the **Costs** page. The older `RERUN_CHECKLIST.md` is about the compression fix; this one is about the required-source rule.

## Human-verified sources (new, optional)
If the team has sources a person already checked (for example the links in the human scoring files), mark them in the Sources workbook **before Step 1**: set **Human-Verified?** (the last column of the Citation Sheet) to **Yes**. It is free and changes nothing until you run a step. The app still opens and saves every such link, and the AI still has to quote it word for word: the mark never replaces the quote, the zero rule, the scan or the cut-off.
- **Step 1** never clears the mark. A marked row that opens stays Verified and in use. If the assessor doubts it, it stays in use and Needs Attention asks for a look. If the app cannot open it, it becomes Human Verification Required and Needs Attention lists it: save a copy by hand (`evidence/manual/<Citation ID>.pdf`). A **Use for Answers? = No** you set always stays No.
- **Step 2** shows the AI the mark, reads such sources first, and an answer whose main citation is one of them has the status **Answered — Human-Verified Source**.
- **Compare** gets a **Source origin** column and **Human-verified source available?** column, and splits coverage, agreement and false zeros by origin. Read both tables: a row the AI left blank cites nothing, so it counts as App-found.
- To stop using the mark, set `human_verified_sources: off` in `agent_setup/categories/parastatal.md` and restart the app (the column itself is always kept).

## What changed, in one paragraph
For Parastatal, a score of 0 is now allowed only when every source the question requires is in the agency's Citation Sheet and was read, and a code scan of the full text of those sources finds nothing relevant. Otherwise the score stays blank and the note says "Missing: <document>" (or "Blocked: ..." when the scan finds text). Step 1 now searches for those required documents, opens the menu links of each agency's confirmed home page (up to 15 pages), and lists what is still missing on the **Needs Attention** sheet. The methodology's own zero condition has precedence over the prompts' older "affirmative absence" rule. ULG is unchanged. A score the template **calculates** as 0 from "No" or empty Yes/No inputs (for example DPG 2b) gets the same check in Step 3: if a required document is missing or the scan finds text, those inputs are left blank for a person. The crawl is **strict** by default: any menu link that did not open makes it incomplete. To ignore dead links whose text and address name no topic word, set `crawl_incomplete_on_dead_link: lenient` in the same file and restart the app (a dead link that does name a topic word still counts). To go back to the old behaviour, set `required_sources: off` in `agent_setup/categories/parastatal.md` (and `crawl_max_pages: 0` to stop the crawl), then restart the app.

## 0. Before the first run (about 10 minutes, no cost)
1. **Restart the app:** close the Terminal window that runs it, then double-click `Start ASICS.command`. Without a restart the new code and prompts are not used.
2. **Save copies of the unopened sources** (free; this is the cheapest gain). Follow `docs/UNOPENED_SOURCES.md`: 11 distinct sources, among them the Bhubaneswar shared laws (`ALL-01`, a scanned PDF, and `ALL-02`, which timed out) and the WATCO website pages. Save each as `evidence/manual/<Citation ID>.pdf` in the city's folder and set **Use for Answers?** to Yes. Do this **before Step 1**, so Step 1 reads your copies.
3. Open **Costs** once, so you know where each run's cost will appear.

## Facts that decide the order (unchanged) [V]
- Step 3 reads only the latest Step 2 file of a city, so **tick every parastatal of the city in Step 2**.
- Step 3 refuses a city whose Sources workbook is newer than its latest Step 2 file. Order: Step 1, your review in Excel, Step 2, then Step 3. Do not save the Sources workbook or run Step 1 after Step 2.
- **New:** the prompts and the Step 3 check changed, so Step 2 and Step 3 must be run **together** after this change. Step 3 reads the "ZERO-CHECKED" mark that Step 2 writes in its notes; old Step 2 answers have none.

## Run 1. Step 1 for Bhubaneswar (page "Step 1 · Find sources")
- **City:** Bhubaneswar. **Category:** Parastatal. **Full refresh:** OFF.
- **At the parastatal review:** tick **BDA, WATCO, CRUT**. Leave OWSSB unticked.
- **Expected cost:** about **$3.5 to $5**, 15 to 30 minutes. The base is the 17 Nov run ($2.15); the site crawl adds at most **about $0.35 to $0.48 for each agency** (15 pages, one assessor call each, about $0.023 to $0.032), so up to about $1.0 to $1.4 for three; the finder now sees the "Check" and "Requires" lines (a few thousand more input tokens per call: a few cents).
- **Check afterwards** (City files, the Sources workbook):
  - The home page row of each agency says `SITE-CRAWL: complete, N of N menu links captured.` or `SITE-CRAWL: incomplete, ...` with the reason. An incomplete or missing crawl keeps every "is it on the website?" question blank.
  - **Needs Attention**: one line per agency and missing document ("missing required source: Town and Country Planning Act [TCP] ... Questions affected: ..."), and one per required source that did not open.
  - WATCO and CRUT: a [CONSTITUTION] row (MoA/AoA, incorporation order or board resolution). **These may not be online**; if none is found, their legal questions stay blank with "Missing: constitution document".
  - The Notes of new rows may end "Meets what the questions require: yes / partly / no".
- **Then, free, in Excel:** open the Sources workbook, switch off anything unsuitable, add pages you trust as team rows, save and close.

## Run 2. Step 1 for Bengaluru (same page)
- **City:** Bengaluru. Full refresh OFF. At the review tick **BDA, BMTC, BWSSB**; the others stay unticked.
- **Expected cost:** about **$3.5 to $5.5** (a repeat run skips discovery and website profiling, about $1.4 less than the 16 Nov run; the crawl adds up to about $1.0 to $1.4; the finder now searches every question that still lacks a required document, not only questions with no source).
- **Expect:** `kbda.karnataka.gov.in` and `eng.bdabangalore.org` pages may still fail (the site redirects, or times out): they will show in Needs Attention and `UNOPENED_SOURCES.md`.

## Run 3. Step 2 for Bhubaneswar, Run 4. Step 2 for Bengaluru (page "Step 2 · Answer questions")
- **Parastatals:** all three of the city, every time. **Sections:** all. "Only these questions" empty.
- **Expected cost:** about the same as before, **$5 to $8** and **$11**, up to 5% more (the message now carries the zero condition, the required sources and up to 5 scan passages).
- **Check afterwards** (the answers workbook, Notes column): count the notes that contain
  - `ZERO-CHECKED:` (a zero the gate allowed; Confidence is Medium),
  - `Missing:` (the score stayed blank because a required source is missing),
  - `Blocked:` (the scan found relevant text, so a zero for "nothing found" was refused),
  - `SOURCE DID NOT OPEN` (Status Human Verification Required).

## Run 5. Step 3 for both cities (page "Step 3 · Score")
- **Cities:** Bhubaneswar, then Bengaluru. All sections. Expected cost **$1 to $2** each.
- **Check afterwards:** rows left for a person with "Zero not allowed: ..." (the check ran again and a required source is now missing or the scan found text; this includes calculated zeros from "No" inputs), and Scorer Comments with "Zero allowed by the required-source check".

## Run 6 (free). Compare (page "Scores", Compare)
- **New sheet "AI zeros":** every row where the AI wrote a 0. Read it from the left: **Route** (Step 2 ZERO-CHECKED, Step 3 typed, Step 3 calculated, or a Step 2 zero backed by a quote), **Gate result (today)**, **Required documents** (each one present, MISSING or did not open), **Scan result**, then the **Human score** and **Agree?**. "No: false zero" means the AI wrote 0 where a person gave points; those rows come first and the Summary counts them.
- **Cities:** Bengaluru and Bhubaneswar. The Summary now has a **Candidate 0** line: rows where a person scored 0 and the AI left the score blank **because a required source is missing**, with a count for each missing document. Use it to decide what to add next.
- **Baseline to beat:** the AI scored **21 of 201** human-scored rows, **agreement 86%**.

## What to expect from the zero rule (honest numbers)
These come from a free test on the 125 rows where people scored 0 and the AI left the score blank (Bengaluru and Bhubaneswar). They measure what the gate and scan would let through, **not** whether a zero is correct.

| | Rows (of 125) allowed as 0 |
|---|---|
| **Today**, with the sheets as they are and every required source present or not | **about 10** (about 5 until a crawl has run, because website questions need a complete crawl) |
| **Best case (a):** every Step 1 gain **except** constitution documents (missing documents found, unopened sources saved, every crawl complete) | **57** |
| **Best case (b):** every gain **including** constitution documents of WATCO, CRUT and the others | **80** |
| **Rough expectation** if the new documents trigger the scan as often as the 32 already scanned (22 of those were blocked) | **about 31 for (a), about 39 for (b)** [A] |

- **Best cases are upper bounds.** They assume every missing document is found, every unopened source opens, every crawl is complete, and the scan finds nothing in documents it has not read yet. The WATCO and CRUT **constitution documents may not be online**, so (b) may be out of reach and (a) is the safer ceiling for them.
- The earlier figure "about 39" came from a looser test (no Rules rule, no extra website page, every agency assumed to have its Act). It is **not** the strict best case. Under the strict table the best cases are 57 and 80, and the rough expectation happens to be close to 39 for (b).
- The scan is strict on purpose: a passage with a topic word and a related word blocks the zero. If too many zeros are blocked, tell me which questions and I will loosen their word lists.

## What NOT to run
- Full refresh ON; Step 2 for only some parastatals; Step 1 or a save of the Sources workbook after Step 2; practice mode.
- Step 3 without a fresh Step 2 after this change (Step 3 would not see the ZERO-CHECKED marks).

## Cost summary [A]
| | Cost |
|---|---|
| Bhubaneswar: Step 1, Step 2, Step 3 | about $10 to $15 |
| Bengaluru: Step 1, Step 2, Step 3 | about $16 to $19 |
| **Everything** | **about $26 to $34** |
