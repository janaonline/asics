# Required sources that are in the Citation Sheet but did not open

Written for the research team. These pages and documents are already in the Citation Sheets of Bengaluru and Bhubaneswar, and a question needs them before the AI may give a score of 0. The automatic check could not open them, so the tool cannot use them. A person can usually open them in a browser. **11 distinct sources** are listed. In the free test of the 125 rows where people scored 0 and the AI left the score blank, 23 rows were blocked only because a required source did not open; they come from 8 of these sources. The other sources here are needed by rows that are also missing something else. Nothing was changed in any Sources workbook, and only addresses already in the Citation Sheets are listed.

## What to do for each source below

1. Open the address in your browser. Check that it is the right page or document, for the right agency.
2. Print the page to PDF, or save it as PDF (browser menu: Print, then "Save as PDF"). For a PDF that is already a document, download it.
3. Save the file in the city's folder as `evidence/manual/<Citation ID>.pdf`, using the Citation ID in the table. For example `outputs/Parastatal/cities/bhubaneswar/evidence/manual/WATCO-01.pdf`. A shared law has an `ALL-` ID, for example `ALL-02.pdf`. The tool reads this copy with the same checks as an opened link.
4. For a **scanned PDF** (a picture of the pages), the tool cannot read it. Save a copy with readable text instead (a text version of the Act from the legislature's site, or copy the text into a `.txt` file) under the same name, for example `ALL-01.txt`.
5. In the **Citation Sheet**, set **Use for Answers?** to **Yes** for that row. The row keeps its Citation ID, so you do not need a new row. Add a new team row only when the address itself is wrong: give the agency ID (or "All parastatals"), the title, the correct URL, and start "What This Source Is Useful For" with the same tag(s) as in the table (for example `[TCP]`).
6. Run Step 1 again (or Step 2). Needs Attention says if a saved copy cannot be used.

Tags in square brackets are how the tool knows what a source is for. Keep them when you edit a row.

## The sources

| City and agency | Citation ID | Address (as in the Citation Sheet) | Why it did not open | What it is for | Questions that need it |
|---|---|---|---|---|---|
| Bengaluru: BDA | BDA-01 | https://kbda.karnataka.gov.in | The site sent a page the tool could not read (DecodingError). A later code fix may let Step 1 open it, so run Step 1 before saving a copy. | [WEB] | DPG 5b, DPG 5c, DPG 5e, DPG 5h, DPG 6, DPG 7c, SC 5b, SC 7b, SC 8b |
| Bengaluru: BDA | BDA-22 | https://oldeng.bdabangalore.org/ | The website did not answer the automatic check (connection timed out). A person can usually open it in a browser. | [WEB] [WEB-FEATURE] | DPG 5b, DPG 5c, DPG 5e, DPG 5h, DPG 6, DPG 7c, SC 5b, SC 7b, SC 8b |
| Bengaluru: BDA | BDA-25 | https://eng.bdabangalore.org/ | The website did not answer the automatic check (connection timed out). A person can usually open it in a browser. | [WEB] [WEB-FEATURE] | DPG 5b, DPG 5c, DPG 5e, DPG 5h, DPG 6, DPG 7c, SC 5b, SC 7b, SC 8b |
| Bengaluru: BDA | BDA-29 | https://bda.karnataka.gov.in | The page is not there (HTTP 404). The address may be old or wrong. | [WEB] | DPG 5b, DPG 5c, DPG 5e, DPG 5h, DPG 6, DPG 7c, SC 5b, SC 7b, SC 8b |
| Bengaluru: BWSSB | BWSSB-05 | https://www.indiacode.nic.in/bitstream/123456789/7905/1/11_of_1963_(e).pdf | The server was too slow to answer (ReadTimeout). India Code is often slow. | [TCP] | DPG 8a, UPD 1a, UPD 2a |
| Bengaluru: BWSSB | BWSSB-27 | https://site.bbmp.gov.in/revised%20masterplan%20(1).html | The website did not answer the automatic check (connection timed out). A person can usually open it in a browser. | [PLANS] [TCP] | DPG 8a, DPG 8b, UPD 1a, UPD 1b, UPD 2a, UPD 2b |
| Bhubaneswar: all parastatals (shared law); needed for BDA, CRUT, WATCO | ALL-02 | https://www.indiacode.nic.in/bitstream/123456789/15210/1/scan_25_jul_2020_compressed.pdf | The server timed out (HTTP 504) when the tool tried. | [ACT] [TCP] | DPG 2b, DPG 8a, SC 4a, SC 5a, SC 8a, SC 10, UPD 1a, UPD 2a, UPD 2c |
| Bhubaneswar: all parastatals (shared law); needed for BDA, CRUT, WATCO | ALL-01 | https://prsindia.org/files/bills_acts/acts_states/odisha/2003/Act11of2003Odisha.pdf | The PDF is a scan: 399 of its 420 pages have no readable text. Needs a copy with readable text (see step 4). | [ULG-LAW] | DPG 1b, DPG 2a, DPG 2b, DPG 8a |
| Bhubaneswar: WATCO | WATCO-01 | https://watcoodisha.nic.in/ContactUs.aspx/Forms.aspx | The website did not answer the automatic check (connection timed out). A person can usually open it in a browser. | [BOARD-LIST] [CHARTER] [GRIEV] [IDENTITY] [PROCURE] [RTI] [WEB] [WEB-FEATURE] | DPG 2a, DPG 3, DPG 5a, DPG 5b, DPG 5c, DPG 5d, DPG 5e, DPG 5f, DPG 5h, DPG 6, DPG 8b, SC 4b, SC 5b, SC 6b, SC 7b, SC 8b, UPD 1b |
| Bhubaneswar: WATCO | WATCO-04 | https://watcoodisha.nic.in/assets/pdf/EOI-962.pdf | The website did not answer the automatic check (connection timed out). A person can usually open it in a browser. | [WEB] | DPG 2a, DPG 3, DPG 5a, DPG 5b, DPG 5c, DPG 5d, DPG 5e, DPG 5f, DPG 5h, DPG 6, DPG 8b, SC 4b, SC 5b, SC 6b, SC 7b, SC 8b, UPD 1b |
| Bhubaneswar: WATCO | WATCO-05 | https://watcoodisha.nic.in/KnowYourComplaintStatus.aspx | The website did not answer the automatic check (connection timed out). A person can usually open it in a browser. | [GRIEV] [WEB-FEATURE] | DPG 5a, DPG 5b, DPG 5c, DPG 5d, DPG 5e, DPG 5f, DPG 5h, DPG 6, DPG 8b, SC 4b, SC 5b, SC 6b, SC 7b, SC 8b |

## Notes

- A page that **opens** but is judged not useful (for example BWSSB-37, a menu page with no content) is not listed: it opened. It is a different problem.
- A source that is **not in the Citation Sheet at all** (for example the constitution documents of WATCO and CRUT, a Rules document, a Town and Country Planning Act) is a Step 1 search gap. The Needs Attention sheet lists those after the next Step 1 run.
- The shared laws (`ALL-01`, `ALL-02`) matter most for Bhubaneswar: every agency there needs them.
