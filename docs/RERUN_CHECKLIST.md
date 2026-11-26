# Re-run checklist (steps you do on the portal)

Written 17 Nov 2026. Only the steps **you** run on the portal (`Start ASICS.command`), in order. Costs are estimates **[A]** from the 16 Nov usage files
(Step 1 Bengaluru $3.91, Bhubaneswar $1.97; Step 2 $10.93 and $5.07; Step 3 $1.42 and $0.35) and show on the **Costs** page afterwards. Nothing here is run for you.

## 0. Before the first run (about 5 minutes, no cost)
1. **Your local `.env`** (the file that holds your key; I was not allowed to edit it). A copy is already saved as `.env.backup`. Change only two lines:
   add `ASICS_FIND_SOURCES_MAX_USES=10`, and delete `ASICS_WEB_SEARCH_MAX_USES=8` (nothing reads it).
2. **Restart the app:** close the Terminal window that runs it, then double-click `Start ASICS.command`. Without a restart the link fix and the new setting are not used.
3. Open **Costs** once, so you know where each run's cost will appear.

## Three facts that decide the order [V]
- **Step 3 reads only the latest Step 2 file of a city.** Step 2 on the portal can tick individual parastatals, but runs are not merged: a Step 2 run for one parastatal leaves the others without answers in Step 3.
  **So always tick every parastatal of the city in Step 2** (the whole-city cost below).
- **Step 3 refuses a city whose Sources workbook is newer than its latest Step 2 file.** So: Step 1, then your review and edits in Excel, then Step 2, then Step 3.
  Do not save the Sources workbook, or run Step 1, after Step 2.
- **A link that failed before and opens now:** Step 1 now switches its "Use for Answers?" to Yes (only if it was No because the link could not be opened; your own ticks and rows you added are never changed).
  Step 2 also re-opens any row marked Yes that is not verified yet, by itself and for free.

## Run 1. Step 1 for Bhubaneswar (page "Step 1 · Find sources")
- **City:** Bhubaneswar. **Category:** Parastatal. **Full refresh:** leave it OFF (a tick would search everything again).
- **When it pauses for the parastatal review:** tick **BDA, WATCO, CRUT**. Leave **OWSSB unticked** (it is marked NEEDS REVIEW; it does not belong to this comparison).
- **Expected cost:** about **$3 to $4**, 10 to 20 minutes. It re-checks all 32 existing rows (about $0.03 each) and searches with the new limit of 10 per call.
- **Check afterwards** (City files page, Bhubaneswar Sources workbook): BDA verified rows (baseline: 9 of 24), WATCO (1 of 3), CRUT (0 of 3); any notes starting "CONFIRM: ... candidate website"
  (a site that is not confirmed as official). The register now names the city government, so the agents are told it.
- **Then, free, in Excel (before Run 3):** open the Sources workbook, switch off anything unsuitable, and add the homepages you trust for WATCO and CRUT as rows ("Your team"). Save and close it.

## Run 2 (optional). Step 1 for Bengaluru (same page)
- **Decide first.** Without it, Step 2 (Run 4) already reopens the 14 BMTC rows that are marked Yes and failed only because of the compression fault (free).
  Run this only if you also want the rows marked No that failed the same way (4 BMTC, 5 BDA) and fresh authority scores and effective dates for every row.
- **City:** Bengaluru. Full refresh OFF. At the review tick **BDA, BMTC, BWSSB**; BMRCL, BMRDA, KRIDE and BMLTA stay unticked (they are already "Include? = No").
- **Expected cost:** about **$3 to $5** (the 16 Nov run cost $3.91; the assessor part is $1.78 for 55 links).
- **Expect:** `kbda.karnataka.gov.in` rows stay unverified until BDA's "Official Website" cell on the Parastatals sheet is set to `bdakarnataka.in`; even then its pages show 0 readable words (they need JavaScript), so a person must save them.
  The India Code scans (6 links) still fail: India Code answers HTTP 504.

## Run 3. Step 2 for Bhubaneswar (page "Step 2 · Answer questions")
- **City:** Bhubaneswar. **Parastatals to answer:** all three (**BDA, WATCO, CRUT**). **Sections:** all. Leave "Only these questions" empty.
- **Before you press Run:** the city line shows "N citation(s) ready to use" (baseline: 10, which is BDA 9 and WATCO 1). It should now be clearly higher.
- **Expected cost:** about **$5 to $8**, 25 to 40 minutes (batch).
- **Check afterwards** (baseline for Bhubaneswar, 168 applicable answers: 113 Insufficient Evidence, 46 Partially Answered, 9 Human Verification Required, 0 Answered; CRUT: 45 of 61 say "no usable source").

## Run 4. Step 2 for Bengaluru (same page)
- **City:** Bengaluru. **Parastatals to answer:** all three (**BDA, BMTC, BWSSB**), never only one. **Sections:** all.
- **Expected cost:** about **$11** (the whole city; ticking one parastatal does not make the file smaller for Step 3).
- **Check afterwards** (baseline, 168 applicable answers: 72 Insufficient Evidence, 73 Partially Answered, 11 Human Verification Required, 12 Answered). BMTC should read more sources than the 9 it had.
  Look at the Needs Attention sheet for "this link couldn't be opened" lines.

## Run 5. Step 3 for both cities (page "Step 3 · Score")
- **Cities:** Bhubaneswar, then Bengaluru (one at a time is fine). **Sections:** all. Leave the question list empty (all questions). Step 3 scores every parastatal of the city; it cannot pick one.
- **Expected cost:** about **$1 to $2** each. It refuses with a clear message if the Sources workbook was saved after Step 2.
- **Check afterwards** (baseline: Bengaluru 43 of 116 rows scored, 73 left for a person, of which 67 "Step 2 found no evidence" and 6 the shared-law message; Bhubaneswar 9 of 116).
  The shared-law message "Step 2 cited ALL-01 ..." should be gone.

## Run 6 (free). Compare (page "Scores", Compare)
- **Cities:** Bengaluru and Bhubaneswar. It now shows **Coverage** (AI scored of human scored) and **Agreement when both scored** as two separate numbers.
- **Baseline:** before the fixes the AI scored **14 of 201** human-scored rows, **none for Bhubaneswar**.

## What NOT to run
- **Full refresh ON** (re-searches every question for every parastatal; more cost, no need).
- **Step 2 for only some parastatals** (Step 3 then loses the others).
- **Step 1 or a save of the Sources workbook after Step 2** (Step 3 will refuse until Step 2 is run again).
- **Practice mode** (it is a made-up city; free but unrelated).
- **Run steps with all three steps at once for both cities** unless you have already done the review in Excel: the pause is the only place you can fix the Sources workbook.

## Re-check links: is it enough after the fix?
**No.** The page re-opens every link (free, no model) but writes the results into a **copy** of the workbook; the Sources workbook that Step 2 reads is **not** changed.
Use it only to look before sharing.

| Option for Bengaluru | What it does | Cost |
|---|---|---|
| Step 2 only (Run 4) | Re-opens the 14 BMTC rows marked Yes and uses them; rows marked No stay unused; no new authority scores or dates | about $11 |
| Step 1 (Run 2) then Step 2 | Recovers rows marked No too, and re-assesses every row (authority, effective date, cut-off) | about $3 to $5, then about $11 |
| Re-check links | Looks only; changes nothing Step 2 uses | free |

## Cost summary
| | Cost |
|---|---|
| Bhubaneswar: Step 1, Step 2, Step 3 | about $9 to $14 |
| Bengaluru: Step 2, Step 3 (without Step 1) | about $12 to $13 |
| Bengaluru: optional Step 1 | about $3 to $5 more |
| **Everything** | **about $21 to $32** |

## Baseline to compare against
- Before the fixes the AI scored **14 of 201** human-scored rows, none for Bhubaneswar.
- **Bhubaneswar** Sources workbook: BDA 24 rows, 9 verified; WATCO 3 rows, 1 verified; CRUT 3 rows, 0 verified; the shared laws (2 rows) 0 verified.
- **Bengaluru** rows not verified in the latest Sources workbook (75: BDA 24, BMTC 26, BWSSB 25):

| ID | Use | Status | Why it failed | Link |
|---|---|---|---|---|
| BDA-01 | No | Not verified | DecodingError (compressed page) | `kbda.karnataka.gov.in` |
| BDA-07 | No | Not verified | DecodingError (compressed page) | `kbda.karnataka.gov.in/Townplaning.html` |
| BDA-08 | No | Not verified | DecodingError (compressed page) | `kbda.karnataka.gov.in/Administration.html` |
| BDA-09 | No | Not verified | DecodingError (compressed page) | `kbda.karnataka.gov.in/Ongoingprojects.html` |
| BDA-10 | No | Not verified | DecodingError (compressed page) | `cag.gov.in/en/audit-report/details/6566` |
| BDA-11 | No | Human Verification Required | security certificate | `agkar.cag.gov.in/docs/AR-2012%20(Standalone%20Report%20on%20BDA)/Eng` |
| BDA-12 | No | Not verified | read timed out | `www.indiacode.nic.in/bitstream/123456789/7903/1/12_of_1976_(e).pdf` |
| BDA-14 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/budget.html` |
| BDA-15 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/rti.html` |
| BDA-16 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/organization-1.html` |
| BDA-17 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/constitution-of-authority.html` |
| BDA-18 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/past-commissioners.html` |
| BDA-19 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/contact-us.html` |
| BDA-20 | No | Human Verification Required | connection timed out | `site.bbmp.gov.in/revised%20masterplan%20(1).html` |
| BDA-21 | No | Not verified | metadata only | `www.indiacode.nic.in/bitstream/123456789/21664/1/36_of_2025_(e).pdf` |
| BDA-22 | No | Human Verification Required | connection timed out | `oldeng.bdabangalore.org/` |
| BDA-23 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/information-related-to-prr-tender.html` |
| BDA-24 | No | Human Verification Required | connection timed out | `upload.indiacode.nic.in/showfile?actid=AC_KA_71_402_00001_11_1552283` |
| BDA-25 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/` |
| BDA-26 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/services-under-sakala.html` |
| BDA-28 | No | Human Verification Required | connection timed out | `propertytax.bdabangalore.org/grievance` |
| BDA-29 | No | Not verified | HTTP 4xx | `bda.karnataka.gov.in` |
| BDA-31 | No | Human Verification Required | scanned / no text | `prsindia.org/files/bills_acts/bills_states/karnataka/2026/Bill16of20` |
| BDA-32 | No | Human Verification Required | connection timed out | `eng.bdabangalore.org/finance-section.html` |
| BMTC-01 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/english` |
| BMTC-02 | Yes | Not verified | assessor: does not support the use | `www.transport.telangana.gov.in/html/pdf/The_Road_Transport_Corporati` |
| BMTC-03 | No | Human Verification Required | Re-tested this run. Previous status: Not verified. | `cag.gov.in/uploads/download_audit_report/2024/BMTC-CAG-Report-Englis` |
| BMTC-08 | No | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/page/RTI/RTI+4(1)+B/en` |
| BMTC-09 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Directors+List/en` |
| BMTC-10 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-4/BMTC+Tenders/en` |
| BMTC-11 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Officers+List/en` |
| BMTC-12 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/` |
| BMTC-13 | No | Not verified | DecodingError (compressed page) | `bengaluruurban.nic.in/en/scheme/shakti-scheme/` |
| BMTC-14 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Perfomance+Indicator/en` |
| BMTC-15 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/BMTC+Glance/en` |
| BMTC-16 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/page/Contact+Us/en` |
| BMTC-17 | No | Human Verification Required | scanned / no text | `crm.mybmtc.com/` |
| BMTC-18 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Departments/en` |
| BMTC-19 | No | Not verified | read timed out | `www.indiacode.nic.in/bitstream/123456789/13047/1/the_road_transport_` |
| BMTC-20 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Rules+And+Regulations/en` |
| BMTC-21 | No | Not verified | metadata only | `www.indiacode.nic.in/bitstream/123456789/21664/1/36_of_2025_(e).pdf` |
| BMTC-23 | No | Not verified | read timed out | `www.indiacode.nic.in/bitstream/123456789/7905/1/11_of_1963_(e).pdf` |
| BMTC-27 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-3/Student+Pass/en` |
| BMTC-28 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-4/Press+Releases/en` |
| BMTC-29 | No | Not verified | assessor: does not support the use | `finance.karnataka.gov.in/info-2/2024-25/Budget+Volumes+2024-25/en` |
| BMTC-31 | No | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Organization+Structure/en` |
| BMTC-32 | Yes | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-1/Vision+and+Mission/en` |
| BMTC-33 | No | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/new-page/Passenger%20bus%20fares/en` |
| BMTC-34 | No | Not verified | DecodingError (compressed page) | `mybmtc.karnataka.gov.in/info-3/Other+Pass/en` |
| BMTC-35 | No | Human Verification Required | connection timed out | `site.bbmp.gov.in/revised%20masterplan%20(1).html` |
| BWSSB-03 | No | Not verified | read timed out | `www.indiacode.nic.in/bitstream/123456789/7908/1/36_of_1964(e).pdf` |
| BWSSB-05 | No | Not verified | read timed out | `www.indiacode.nic.in/bitstream/123456789/7905/1/11_of_1963_(e).pdf` |
| BWSSB-06 | No | Human Verification Required | connection timed out | `upload.indiacode.nic.in/showfile?actid=AC_KA_71_402_00003_36_1552285` |
| BWSSB-08 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/page/Contact+Us/Board+Members/en` |
| BWSSB-09 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/info-4/Accounts/Budget/en` |
| BWSSB-10 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/new-page/Annual%20Report%202017/en` |
| BWSSB-15 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/info-2/Tender/en` |
| BWSSB-16 | Yes | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/page/Contact+Us/Contact+Info/en` |
| BWSSB-17 | No | Human Verification Required | blocked to automated tools | `www.bwssb.gov.in/sakala_services` |
| BWSSB-18 | No | Human Verification Required | connection timed out | `saiindia.gov.in/webroot/uploads/download_audit_report/2014/Karnataka` |
| BWSSB-19 | No | Not verified | DecodingError (compressed page) | `cag.gov.in/ag1/karnataka/en/audit-report/details/118178` |
| BWSSB-20 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/page/Contact+Us/Senior+Management/en` |
| BWSSB-21 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/page/Contact+Us/Other+Offices/en` |
| BWSSB-22 | No | Not verified | metadata only | `www.indiacode.nic.in/bitstream/123456789/21664/1/36_of_2025_(e).pdf` |
| BWSSB-24 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/page/Contact+Us/Service+Station/en` |
| BWSSB-26 | No | Human Verification Required | blocked to automated tools | `www.bwssb.gov.in/complaint` |
| BWSSB-27 | No | Human Verification Required | connection timed out | `site.bbmp.gov.in/revised%20masterplan%20(1).html` |
| BWSSB-31 | No | Human Verification Required | blocked to automated tools | `bwssb.gov.in/index.php` |
| BWSSB-32 | No | Not verified | assessor: does not support the use | `aciwrm.karnataka.gov.in/info-1/Karnataka+State+Water+Policy+2022/en` |
| BWSSB-35 | No | Not verified | assessor: does not support the use | `finance.karnataka.gov.in/info-2/2024-25/Budget+Volumes+2024-25/en` |
| BWSSB-37 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/info-4/Technical/Waste+Water+Management/en` |
| BWSSB-39 | No | Not verified | assessor: does not support the use | `bwssb.karnataka.gov.in/info-4/Technical/Maintenance/en` |
| BWSSB-44 | No | Not verified | Re-tested this run. Previous status: Not verified. | `dpar.karnataka.gov.in/dpar_tnn/en` |
| BWSSB-45 | No | Human Verification Required | scanned / no text | `kppp.karnataka.gov.in/` |
| BWSSB-46 | No | Human Verification Required | scanned / no text | `censusindia.gov.in/nada/index.php/catalog/584` |
