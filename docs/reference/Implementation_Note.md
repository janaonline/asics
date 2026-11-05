# Parastatal Templates and Consolidated Scoring - Implementation Note (updated)

Keep all four files in ONE OneDrive folder with these exact names:
`Parastatal_UPD_Template.xlsx`, `Parastatal_SC_Template.xlsx`, `Parastatal_DPG_Template.xlsx`, `Parastatal_Consolidated_Scoring.xlsx`. The source workbook was only read.

## 1. Question worksheets (one per scored question or sub-question)
Sheet names are question codes with a space ("UPD 1a", "SC 4a", "DPG 5a"). The source writes codes inconsistently ("DPG5a", "SC - 6b"); the original is kept in `Question_Index`.

| Workbook | Sheets |
|---|---|
| UPD (14) | UPD 1a, 1b, 2a, 2b, 2c, 2d, 3a, 3b, 4a, 4b, 5a, 5b, 6a, 6b |
| SC (18) | SC 1, 2, 3 (standalone); 4a, 4b, 5a, 5b, 6a, 6b, 7a, 7b, 8a, 8b; SC 9, 10, 11 (standalone); 12a, 12b |
| DPG (20) | DPG 1a, 1b, 2a, 2b; **DPG 3**; **DPG 4**; 5a-5h; DPG 6; 7a, 7b, 7c; 8a, 8b |

Besides the standalone questions in the brief, the source also has **DPG 3** and **DPG 4** without sub-questions, so they have sheets too. A master question with sub-questions (UPD 1, SC 4 ...) has no sheet; it is the SUM of its sub-questions.
Each sheet: exact question, methodology, evidence requirement, applicability, notes; one table with City, Parastatal Name, Type, Question Code, Description, Max Score, response fields, Score, Chapter / Provision / Clause / Page, Scorer Comments, Additional Comments, Source Link, Latest Information date, Key, Record Check. Bengaluru rows are pre-filled for the types each question applies to. Scores are typed by the scorer (validated 0 to Max), except where the methodology gives a calculation (SC 1, 2, 3, 11, 12b; DPG 1a, 2b, 7a) - there the inputs are fields and Score is a formula.

## 2. City and parastatal configuration
`Configuration` in each workbook: City list, Parastatal Type list (Development Authority, Water Supply Entity, Public Bus Transport Operator), and the main table (City, Type, Name, Active). Active = Y rows become columns in Raw Summary (120 max); up to 40 cities. Bengaluru = BDA, BWSSB, BMTC. Bhubaneswar is a placeholder (Active = N).
Capacity was raised from 30 slots / 20 cities to 120 slots / 40 cities on request (expected maximum: 40 cities x 3 parastatals).
Consistency: each workbook shows a configuration checksum (Raw Summary F2); the consolidated workbook compares them and matches every value by City or City|Parastatal key, so a mismatch shows "CHECK CONFIG", never a wrong number.
**Add a city:** add it to the City list; add its parastatals in the main table (Active = Y); repeat in the other two workbooks with identical spelling; add rows under each question table (drop-downs).

## 3. How data flows
Question tables -> `Raw Summary Detail` (long format: City, Type, Parastatal, Score, Response, Evidence, Remarks, Status) -> `Raw Summary` (layout of "Individual parastatal score") -> `City Summary` (city level). All formulas use table references, so new rows are picked up. Blank = not answered (never 0); NA = does not apply; a real 0 shows as 0. Only the first row per City + Parastatal is used, so nothing is double counted.

## 4. Scoring rules used in the summaries (from the pilot "Summary (tentative)" sheet and your Raw sheet 3 image)
- **Parastatal level** (Raw Summary rows 8-10): score out of 10 = sum of the scored MQ scores / their attainable max x 10. An MQ counts only when all its applicable sub-questions are answered. "Attainable max" fixes the UPD 2 issue (a parastatal type can only earn 5 of its 10).
- **City level** (City Summary): each question = AVERAGE of the parastatals it applies to; MQ = SUM of its sub-questions; pillar out of 10 = scored MQs / their attainable max x 10. A question counts only when ALL applicable parastatals are scored (otherwise "Partial", left out).
- **Total Score** (sheet "Score across city systems") = average of UPD, DPG, SC, shown only when all three have a score (as on the image).
- **"Score across all questions"** (Block A) = parastatal-level score out of 10 pooled over UPD + DPG + SC; Blocks B and C show the parts and every question.

## 5. Consolidated workbook
Two sheets. `Score across all questions`: Block A (City x parastatal type, Raw sheet 2 layout), Block B (per parastatal with UPD / DPG / SC parts), Block C (all 69 questions x all parastatals). `Score across city systems`: Raw sheet 3 layout - City, UPD, DPG, SC (out of 10) and Total Score.
**Refresh (Excel desktop):** save the category workbooks, open the consolidated file, Enable / Update Links, or Data > Edit Links > Update Values. Source files can stay closed. Links are relative. **Excel for the web cannot refresh external links**; it shows the last values saved by desktop Excel.

## 6. Please confirm
1. The image values (Bengaluru 3.95 / 6.61 / 3.51 / 4.69) cannot be reproduced exactly from the pilot workbook (it gives 3.96 / 6.63 / 8.19 on its own basis). I treated them as illustrative. Please check the rules in section 4 give the intended result.
2. "Score across all questions" is pooled over all scored MQs. If you want the average of the three pillar scores instead, it is a one-line change.
3. The strict "all applicable parastatals scored" rule means a city pillar stays blank until data is complete. Say if you prefer partial results.
4. "DPG 4" is not scored in the source and is left out of every max.
5. Source inconsistencies carried as-is and flagged on each sheet: UPD 1a bands 10 / 2.5 / 0 vs Max 5; SC 12a "top city scores 10" vs Max 5 (score is typed); DPG 7a "1.25" vs 1.11; DPG 7c "3" vs 3.33; DPG 6 text mixes 5 and 10.
6. UPD 3b is "Common" in the source but is a water question - applied to Water Supply Entity only (assumption).
7. SC 1, 2, 3, 11 have conditional applicability in the source (revenue-raising, capex mandate, annual budget, chief executive post); all types are marked applicable until you confirm.
8. SC 2, 12a, 12b score against "the highest city"; the benchmark is a typed field (unclear whether assessed cities or all India).
9. "Parastatal Methodology (DNU)" was not used (name says Do Not Use; wording differs). Wording follows the UPD / SC / DPG sheets.
10. Bhubaneswar parastatals are not loaded (image shows BDA, WATCO, CRUT - unverified). Lucknow, Mumbai, Guwahati are not configured; add them in Configuration.

## 7. Limits
- Duplicate City + Parastatal rows cannot be blocked (Excel allows one validation per cell). They turn red, show "CHECK: DUPLICATE" and are counted in Raw Summary F3 (must be 0).
- Question sheets are not protected (a protected sheet cannot grow a table). Raw Summary, City Summary, Raw Summary Detail and the consolidated sheets are protected without a password.
- Capacity: 120 active City-Parastatal combinations (40 cities x 3 parastatals) and 40 cities per workbook, plus up to 300 Configuration rows. Going over is flagged in Raw Summary F3 and in the consolidated data-issues cell, and the extra rows are left out of the summaries. Capacity can be raised again by rebuilding (two numbers). Block A shows one parastatal per type per city; others appear in Blocks B and C.

## 8. What was tested
In LibreOffice only: zero formula errors in all four files; a full-capacity test (all 40 cities and 120 slots filled, last slot and last city read correctly, one city over the limit flagged); sample data (separate copies, now removed) with hand-checked calculated scores; city and pillar scores checked against an independent Python implementation of the rules for UPD, DPG and SC; value changes, new city-parastatal combinations, different parastatal counts per city, wrong-type and duplicate rows, and configuration mismatch; consolidated formulas run on cached external-link data; wording of all 52 question sheets compared to the source cells; table definitions checked for Excel compatibility.
**Not verified:** opening in desktop Excel / Excel for the web, and a live "Update Links" refresh through OneDrive. Open each file once in desktop Excel and run Update Values before relying on it.
