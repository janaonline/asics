# Methodology audit: does the system use each question's zero condition?

Written 19 Nov 2026. Read-only: no code, prompt or data was changed, no model call or Step 1/2/3 was run.
Marks: **[V]** = read in code or files. **[A]** = assumption or my judgement.
"Scored questions" means the 52 questions that are scored directly (the leaf questions). The bank has 69 questions; the other 17 are roll-ups added up from sub-questions [V].

## Short summary

1. **The team is right: the methodologies do define zero.** 49 of the 52 methodologies give a zero rule: 35 are purely absence-based ("0 if no provision / not found / not on the website"), 11 mix absence with a condition, and 3 are purely condition-based. So 46 of 52 depend wholly or partly on something *not being found*. Only 3 state no zero rule (DPG 4, DPG 7a, SC 12b) [V sentences, A for the class, table in section 5].
2. **The methodology text is sent word for word at Steps 2 and 3, but not at Step 1.** The Evidence / Source Requirement is sent at Steps 1, 2 and 3, but **no prompt tells the model what to do with it** (it is only pasted in). At Step 1 the finder gets the evidence text but not the methodology, and the assessor gets neither [V].
3. **The prompts contain a stricter zero rule than the methodology.** "A rubric 0 needs AFFIRMATIVE ABSENCE ... otherwise it is 'not found', never 0" appears in 5 prompt/skill files. The methodology says "0 if not found". The model follows the prompt rule [V text, A reason].
4. **The effect is large.** People scored 127 zeros for Bengaluru and Bhubaneswar. The AI left **125 of them blank** (98%), gave 1 zero and 1 non-zero. 101 of the 125 blank rows cite the "absence not affirmed" rule or "a 0 is not allowed" in their own notes [V]. Zeros are most of the people-only rows, so they are the main reason AI coverage is low (Bengaluru 52 of 85, Bhubaneswar 73 of 92) [V].
5. **But the AI was often right to be careful.** In about 47 of the 125 rows (38%) the sources the Evidence column names were not in the Citation Sheet at all (for example no parent Act for any Bhubaneswar parastatal, no website pages for BDA Bengaluru). For those the right result is a blank that names the missing source. The rule change below only helps where the sheet is complete, so **Step 1 gaps must be fixed too** [A, proxy in section 8].
6. **Code enforces very little.** Code builds the prompts, checks the quote, checks the BAND number (note only), checks allowed scores, and blanks every score when Step 2 says "Insufficient Evidence". No code reads a zero condition or checks that the sources named in the Evidence column were consulted [V, section 7].
7. **Smallest fix (ranked in section 10):** make the zero rule in the prompts follow the methodology and require the Evidence column's sources to be in the sheet (prompt change, small), then add a small code check that allows a zero only when those sources are present (code, medium).

---

## 1. The fields

**Question-bank columns** (sheet "Question Bank" in `data/question_banks/Parastatal_ASICS_Question_Bank.xlsx`, 12 columns) [V]:
`Sl. No.`, `City-Systems Pillar`, `Question`, `Tag`, `Score / Max Score`, `Assessment Level`, `Unit of Assessment`, `Applicability`, `Detailed Methodology`, `Evidence / Source Requirement`, `Origin`, `Rationale`.
A second sheet, "Bank Info", only names the source file.

- **Max Score** is the column `Score / Max Score`.
- **There is no "Notes for scorers" column in the bank.** The scoring templates (`scoring/2027/templates/Parastatal_*_Template.xlsx`) carry a column `Notes / source discrepancies`. Step 3 sends it to the model [V]. For 33 of the 52 questions it says only "None identified."; 19 have a real note (scale problems, assumptions).
- `Origin` and `Rationale` are empty in all rows [V]. `Rationale` is loaded into the code (`models.py:46`) but is never put in any prompt [V]. `Unit of Assessment` is filled for 64 of 72 rows.
- The bank's Detailed Methodology and the templates' Detailed Methodology are identical for all 52 questions (compared after tidying spaces) [V].

**Empty or placeholder fields among the 52:**

| Field | What I found [V] |
|---|---|
| Detailed Methodology | Never empty. **DPG 4** is a placeholder: only a note saying scoring "has not been undertaken ... awaiting support from the state teams". It has no Max Score. Code detects this (`methodology.py:16-22`) and gives "NO RULE" for a person, with no model call. DPG 7b and DPG 7c contain "(?)" marks. |
| Evidence / Source Requirement | **Empty in the bank for 8 questions: DPG 4, DPG 5f, DPG 7b, DPG 7c, SC 6a, SC 6b, SC 7a, SC 7b.** The templates replace the blank with the text "Not provided in the source workbook." (so Step 3 sees that sentence, Steps 1 and 2 see nothing). DPG 7a only says "Detailed evidence information provided in the methodology column (I 33)". The same generic line, "Website screenshots/archived URLs with date of access, for each document type", is used for 8 questions (DPG 5a to 5e, 5g, 5h, 6). |
| Max Score | Empty only for DPG 4. Six methodologies have a scale or number inconsistency (UPD 1a, UPD 1b and SC 12a: bands above the Max Score; DPG 6 and DPG 7a: numbers that contradict themselves; DPG 7c: "Score 3" with Max 3.33). The template notes say so. |

## 2. Step 1: finding and selecting citations

| Part | Where [V] | Question fields it receives |
|---|---|---|
| **Source finder** (agent `citation-builder`, prompt `find-sources.md`) | `links_builder.py:142-176` (`research`), digest at `links_builder.py:161` | Per question: ID, assessment level, question text, **Evidence / Source Requirement**. **Not** the methodology, max score or applicability. |
| Shared-laws search (one per city) | `sources_master.py:157` | The same digest. |
| Second "fill gaps" search | `links_builder.py:249-274` calls `research` again | The same digest, for questions without a verified source. |
| **Source assessor** (prompt `assess-source.md`) | `common.py:66-91` (`assess_source`) | **No question field at all.** It gets the title, URL, source type, the finder's claimed "useful for" text, and up to 15,000 characters of the page. |
| Re-test of old rows | `links_builder.py:85-130` | No question fields (goes through the assessor). |

**Is the Evidence / Source Requirement used to decide ...?**
- **What to search for:** only because the text is in the model's message. No prompt line says "find the documents the Evidence column names". The finder follows a fixed tag order in the prompt (`find-sources.md:13-32`: Act, Rules, ULG law, T&CP, budget, ...) that is not built from the column [V]. Whether the model honours the column is not checkable in code [A].
- **Which sources to keep:** no. A source is kept if the link opens, has saved text and the assessor says the text supports the finder's own claimed use (`common.py:163-176`) [V].
- **The "useful for" tag:** no. The model writes it from the tag list in the prompt (`find-sources.md:34-62`) [V].
- **Use for Answers:** no. Code sets it to Yes when the link is Verified (`common.py:155`) and to No when the assessor says "not useful" (`common.py:172-176`) [V].
- **Which questions still need a search:** `links_builder.py:79-81` and `237-247` treat a question as covered when any Verified source carries its ID in `question_ids`. The IDs are written by the finder model. So "covered" means *tagged*, not *meets the Evidence column* [V].

**Exact digest text sent to the source finder** (output of `question_digest`, `common.py:53-57`) for 3 questions:

```text
- UPD 1a [Law/Policy] Is the parastatal mandated to prepare its spatial and/or sectoral plans in coordination with the ULG(s) within its jurisdiction?
  Evidence: Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act.
- DPG 5a [Implementation] Annual budget
  Evidence: Website screenshots/archived URLs with date of access, for each document type
- SC 10 [Law/Policy] Does the law mandate a minimum tenure for the executive authority of the parastatal?
  Evidence: Relevant Parastatal Act; rules governing appointment, tenure and removal of the executive authority/chief executive.
```

## 3. Step 2: answering

**What the model receives** [V]: system prompt = `shared-rules.md`, then the skills `scoring-methodology` and `india-code-and-acts`, then the section skill (UPD, DPG or SC), then the task prompt `answer-question.md` (`agent_setup.py:142-153`). Team memory notes go at the top of the message. The question block is built in `agents/sections/base.py:156-167` (`_question_block`) and followed by the saved text of up to 8 Citation Sheet sources.

**Yes, the model gets the Detailed Methodology and the Evidence / Source Requirement word for word** [V], as the four real blocks below show (Bengaluru, BWSSB). The only text that refers to the Evidence column is a screenshot hint (`answer-question.md:99`, `dpg.md:38`). **No prompt line tells the model to check the sources named in that column** [V].

**Block 1. Law/Policy yes/no (UPD 1a)**
```text
City: Bengaluru, Karnataka. City government (ULG): Greater Bengaluru Authority
Parastatal: Bangalore Water Supply and Sewerage Board (BWSSB), type water_supply_entity
Section: Urban Planning & Design (UPD)
Question UPD 1a [SQ, max score 5]: Is the parastatal mandated to prepare its spatial and/or sectoral plans in coordination with the ULG(s) within its jurisdiction?
Assessment level: Law/Policy
Detailed Methodology:
Check the relevant Parastatal Act/Rules and the State Town and Country Planning Act to determine whether the parastatal is required to coordinate with the ULG(s) while preparing its sectoral plans.
Identify the nature of the ULG’s formal role in the plan-making process and score as follows:
10 — ULG approval/concurrence is mandatory with terms such as 'shall consult' 
2.5 — Consultation with the ULG is discretionary with terms such as “may consult”.
0 — No formal role for the ULG in preparation of the parastatal’s plan can be established.
 
Where different provisions apply to different plans prepared by the parastatal, assess the principal sectoral plan relevant to the service being evaluated.
Evidence / Source Requirement: Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act.
```

**Block 2. Website-feature question (DPG 3)**
```text
City: Bengaluru, Karnataka. City government (ULG): Greater Bengaluru Authority
Parastatal: Bangalore Water Supply and Sewerage Board (BWSSB), type water_supply_entity
Section: Decentralised Participatory Governance (DPG)
Question DPG 3 [MQ, max score 10]: Does the parastatal maintain an active and functional website?
Assessment level: Implementation
Detailed Methodology:
Check the official website of the relevant parastatal.

Score 10 if an official website of the relevant parastatal exists, opens without error, and shows content updated within the last 12 months (verifiable "last updated" date or dated content such as a recent notice/circular). 

Score 0 if no official website is found.
Evidence / Source Requirement: Live URL, screenshot/web-archive capture, date of check of the website of the relevant parastatal
```

**Block 3. Numeric question (SC 1)**
```text
City: Bengaluru, Karnataka. City government (ULG): Greater Bengaluru Authority
Parastatal: Bangalore Water Supply and Sewerage Board (BWSSB), type water_supply_entity
Section: State Capacities (SC)
Question SC-1 [MQ, max score 10]: What proportion of the parastatal's total expenditure is financed through its own revenues?
Assessment level: Implementation (Numeric)
Detailed Methodology:
Check  the ULG's budget documents, record for each year: own revenue (tax and non-tax revenue, excluding all government grants and transfers), other revenue, capital receipts, revenue expenditure and capital expenditure. Enter all amounts in crore and population in lakh. 
Use Actuals where available; otherwise Revised Estimates (RBE); otherwise Budget Estimates (BE); record the type used for each year.

Total expenditure = revenue expenditure + capital expenditure. For each year, own revenue % = own revenue ÷ total expenditure.

Use the average of the latest 3 years available (minimum 2 years), from 2019-20 onwards.

Score = average own revenue % × 10, capped at 10 (e.g. 50% = 5; 100% or more = 10).

If budget data for at least 2 years is not available, score 0.
Evidence / Source Requirement: Annual budget of the last three financial years of the relevant parastatal.
```

**Block 4. Partial-credit question (UPD 3a: Part A and Part B)**
```text
City: Bengaluru, Karnataka. City government (ULG): Greater Bengaluru Authority
Parastatal: Bangalore Water Supply and Sewerage Board (BWSSB), type water_supply_entity
Section: Urban Planning & Design (UPD)
Question UPD 3a [SQ, max score 5]: Is the Water supply entity mandated to consider the needs of women, the urban poor and other vulnerable groups in decisions relating to access, affordability and delivery of water and sanitation services?
Assessment level: Law/Policy
Detailed Methodology:
Check the Water Supply Board/utility Act, rules, tariff regulations and other binding legal instruments. Assess whether the legal framework requires the Board to address the needs of economically vulnerable groups and women in decisions relating to access, affordability and service delivery.
Do not award credit for generic obligations such as “public interest”, “universal supply”, “adequate service” or “service to all” unless these are translated into a specific legal requirement relating to affordability, service access, coverage or the needs of women.
 
Part A – Urban Poor: Affordability and access – 2.5 marks
Look for identifiable legal requirements such as:
concessional, lifeline or differentiated tariffs for EWS/BPL/low-income households;
concessions relating to connection charges, deposits or other service-access costs;
requirements to provide services to slums, informal settlements, low-income or underserved areas;
tenure-neutral or other provisions enabling access irrespective of land tenure/status;
minimum/lifeline supply or alternative service arrangements for underserved populations.
 
Score 2.5: There is a clear mandatory requirement (“shall”, “must” or equivalent) addressing affordability or access for economically vulnerable groups.
Score 1.25: The legal framework permits or encourages such measures (“may” or equivalent), but does not make them mandatory.
Score 0: No specific legal provision addressing affordability or access for economically vulnerable groups is found.
 
Part B – Women: Gender-responsive access and service delivery – 2.5 marks
Look for identifiable legal requirements such as:
consideration of women’s needs in water and sanitation planning or service provision;
requirements relating to location, accessibility or safety of shared/public water infrastructure;
gender-sensitive planning, assessment or consultation requirements;
service or design requirements intended to reduce barriers faced by women in accessing water and sanitation services.
 
Score 2.5: There is a clear mandatory requirement (“shall”, “must” or equivalent) addressing women’s access or service-delivery needs.
Score 1.25: The legal framework permits or encourages consideration of women’s needs (“may” or equivalent), but does not make it mandatory.
Score 0: No specific legal provision addressing women’s access or service-delivery needs is found.
Evidence / Source Requirement: Water supply entity/utility Act, water and sanitation legislation, tariff regulations, service rules, State policies and other applicable binding instruments
```

**How the "up to 8 ranked sources" are chosen** (`base.py:177-220`) [V]:
1. The pool is the Citation Sheet rows marked Use for Answers = Yes, Verified, with saved text. For a Law/Policy question, sources dated after the cut-off or Bills are removed first (`cutoff.screen_sources`).
2. They are sorted by two keys, highest first: (a) whether the finder tagged the source with this question's ID, then (b) a keyword score = the share of query words that appear in the source's text (`links/text.py:127-132`). The query is: question text + methodology + Evidence / Source Requirement + the section's `evidence_hints` keywords (`base.py:181`).
3. The top 8 are kept (`MAX_SOURCES = 8`). Each gets a share of 60,000 characters (at least 4,000), cut to the passages that match the query best (`base.py:215-220`).
4. So the Evidence column is used only as a bag of words inside the query. It is **not** used as a list of named sources, and the ranking is by the finder's tag and by keywords. The model can read more with `read_citation` and `search_citation_sheet` (up to 8 tool calls).
5. Before any model call: a placeholder methodology, an all-late Law/Policy sheet, or "no usable source" end the question with no model call (`base.py:182-230`).

## 4. Step 3: scoring

**Prompt built in** `scoring/template_scoring.py:145-198` (`build_prompt`) [V]. System prompt = `shared-rules.md` + skills `scoring-methodology`, `india-code-and-acts` + `score-question.md`. The model receives:
- Question, applicability, **Detailed Methodology**, then **every template field whose label starts with "Evidence" or "Notes"** (so the Evidence / Source Requirement and `Notes / source discrepancies`, including the text "None identified." and "Not provided in the source workbook."), and the Max Score.
- The input columns, with allowed values.
- **Allowed scores** (`ALLOWED SCORES: ...`) or `PARTIAL CREDIT`, worked out in code from the methodology (`scoring/score_levels.py`). A score outside the list is thrown away, not converted. Zero is always inside the range, and is a listed level whenever the methodology lists one.
- The Step 2 answer: status, answer text, citation ID, quote, and Step 2's notes (class, confidence, BAND and any **SCORE-BLANK reason**). **Not** Step 2's numeric proposed score.
- The ranked text of the cited source (up to 20,000 characters) and the IDs of the other sources.

Real Step 3 prompts (placeholder Step 2 answer; everything above it is the real question data). Three shapes:

**UPD 1a: levels, with the scale note**
```text
City: Bengaluru
State: Karnataka
Parastatal: BWSSB

QUESTION UPD 1a
Question: Is the parastatal mandated to prepare its spatial and/or sectoral plans in coordination with the ULG(s) within its jurisdiction?
Applicability (source): All parastatals excluding Development Authorities
Detailed Methodology: Check the relevant Parastatal Act/Rules and the State Town and Country Planning Act to determine whether the parastatal is required to coordinate with the ULG(s) while preparing its sectoral plans.
Identify the nature of the ULG’s formal role in the plan-making process and score as follows:
10 — ULG approval/concurrence is mandatory with terms such as 'shall consult' 
2.5 — Consultation with the ULG is discretionary with terms such as “may consult”.
0 — No formal role for the ULG in preparation of the parastatal’s plan can be established.
 
Where different provisions apply to different plans prepared by the parastatal, assess the principal sectoral plan relevant to the service being evaluated.
Evidence / Source Requirement: Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act.
Notes / source discrepancies: Source methodology text lists score bands of 10 / 2.5 / 0, but Max Score is 5. Carried verbatim; scorer to confirm the scale with the program team.
Max Score: 5

SCORE: give "score" as a number from 0 to 5 (the points for this row, decided from the methodology's bands).
ALLOWED SCORES: 5 / 2.5 / 0. The Points cell takes 0 to 5: give exactly one of these values. Any other value is discarded, not converted.
The methodology lists a level of 10, which the cell cannot take: enter 5 for it. The other levels are entered as written.

STEP 2 ANSWER
Status: Answered — Verified Source
Answer: ANSWER: (example) ...
Citation ID: BWSSB-01
Quoted evidence: (example quote)
Notes: CLASS: A1; CONFIDENCE: High; BAND: 10

CITATION SHEET SOURCES FOR THIS UNIT:
```

**DPG 2b: Yes/No inputs, one per component**
```text
City: Bengaluru
State: Karnataka
Parastatal: BWSSB

QUESTION DPG 2b
Question: Is the parastatal mandated to submit its plans, budgets or reports to the ULG/council?
Applicability (source): Common — all parastatal types.
Detailed Methodology: Check the relevant Parastatal Act and Municipal Act for provisions requiring the parastatal to submit or table its plans, budgets and reports before the ULG/council.
The requirement may arise either:
through a specific provision applicable to the parastatal (The requirement may be provided through a general provision covering these documents or through specific provisions for each); or
through a general/blanket provision in the Municipal Act requiring public authorities, boards, corporations or other agencies operating within the municipal area to submit specified plans, budgets, reports or related documents to the ULG/council.
 
Score 1.67 points each where:
plans are required to be submitted/tabled;
budgets are required to be submitted/tabled; and
annual/performance reports are required to be submitted/tabled.

Score 0 for each component where no such requirement exists.
 
Where all three are provided for, award the full score of 5.
 
Submission only to the State Government or another authority should not be counted as submission to the ULG/council.
Evidence / Source Requirement: Plan/Budget preparation/Annual report preparation clause of the enabling Act of the relevant parastatal
Notes / source discrepancies: 1.67 points per component (plans, budgets, reports); all three = 5 (as written in the methodology).
Max Score: 5

INPUT COLUMNS (fill each one):
- "Plans required to be submitted or tabled before ULG/council": choose one. Allowed values: Yes / No.
- "Budgets required to be submitted or tabled before ULG/council": choose one. Allowed values: Yes / No.
- "Annual or performance reports required to be submitted or tabled before ULG/council": choose one. Allowed values: Yes / No.

STEP 2 ANSWER
Status: Answered — Verified Source
Answer: ANSWER: (example) ...
Citation ID: BWSSB-01
Quoted evidence: (example quote)
Notes: CLASS: A1; CONFIDENCE: High; BAND: 10

CITATION SHEET SOURCES FOR THIS UNIT:
```

**DPG 3: website question with ALLOWED SCORES**
```text
City: Bengaluru
State: Karnataka
Parastatal: BWSSB

QUESTION DPG 3
Question: Does the parastatal maintain an active and functional website?
Applicability (source): Common.
Detailed Methodology: Check the official website of the relevant parastatal.

Score 10 if an official website of the relevant parastatal exists, opens without error, and shows content updated within the last 12 months (verifiable "last updated" date or dated content such as a recent notice/circular). 

Score 0 if no official website is found.
Evidence / Source Requirement: Live URL, screenshot/web-archive capture, date of check of the website of the relevant parastatal
Notes / source discrepancies: In the source, per-parastatal rows for DPG 3 are tagged SQ with Max 10. Treated here as a standalone MQ (Max 10). Point-in-time check - record the date checked.
Max Score: 10

SCORE: give "score" as a number from 0 to 10 (the points for this row, decided from the methodology's bands).
ALLOWED SCORES: 10 / 0. The Points cell takes 0 to 10: give exactly one of these values. Any other value is discarded, not converted.

STEP 2 ANSWER
Status: Answered — Verified Source
Answer: ANSWER: (example) ...
Citation ID: BWSSB-01
Quoted evidence: (example quote)
Notes: CLASS: A1; CONFIDENCE: High; BAND: 10

CITATION SHEET SOURCES FOR THIS UNIT:
```

(SC 1 shows 18 numeric input columns for three years; omitted for length.)

**The gate before the model** (`scoring/ai.py:327-363`, `check_step2`): if Step 2's status is "Insufficient Evidence", "Not Yet Assessed", blank, or it cites no Citation ID, the model is **not called** and the row is left for a person (`ai.py:350-353`) [V]. This is why 97 of the 125 human-zero rows never reached the Step 3 model.

## 5. Zero conditions in the 52 scored methodologies

Classes: **(a)** absence-based: 0 if not found / not on the website / no provision. **(b)** condition-based: 0 if it does not meet X. **(a)+(b)** both appear (usually Part A is absence-based and Part B is format-based). **(c)** no zero condition stated. I classified each by reading the text [A for the class; the sentences are exact].

| Class | Count |
|---|---|
| (a) absence-based | **35** |
| (b) condition-based | **3** (DPG 1a, SC 10, SC 11) |
| (a)+(b) mixed | **11** (DPG 5a to 5h, DPG 7b, SC 3, SC 9) |
| (c) none stated | **3** (DPG 4, DPG 7a, SC 12b) |
| Total | 52 |

So **46 of 52 (88%)** have a zero rule that depends, wholly or partly, on something *not being found*.

| Code | Level | Class | Exact zero-condition sentence(s) | Evidence / Source Requirement (bank) |
|---|---|---|---|---|
| UPD 1a | Law/Policy | (a) absence-based | 0 — No formal role for the ULG in preparation of the parastatal’s plan can be established. | Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act. |
| UPD 1b | Implementation | (a) absence-based | Score 0 where there is no such evidence. | Evidence may include plan documents, consultation records, meeting minutes, ULG resolutions/comments, responses to ULG inputs, or information published on the parastatal website. |
| UPD 2a | Law/Policy | (a) absence-based | Score 0 if no such provision exists. | Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act. |
| UPD 2b | Implementation | (a) absence-based | Score 0 if there is no identifiable evidence that the Master Plan or its spatial/population framework informs water planning. | Water supply entity's current water supply/sewerage master plan or equivalent sectoral planning document; applicable Master Plan/Development Plan/Metropolitan or Regional Plan; land-use conversion/regularisation records for major treatment plants or trunk infrastructure, where available. |
| UPD 2c | Law/Policy | (a) absence-based | Score 0 if no such provision exists. | Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act. |
| UPD 2d | Implementation | (a) absence-based | Score 0 if there is no identifiable evidence that the Master Plan or its spatial/population framework informs transport planning. | Transport corporation's current mobility/network plan; applicable Master Plan/Development Plan/Metropolitan or Regional Plan; land-use conversion/regularisation records for major transport infrastructure, where available. |
| UPD 3a | Law/Policy | (a) absence-based | Score 0: No specific legal provision addressing affordability or access for economically vulnerable groups is found. / Score 0: No specific legal provision addressing women’s access or service-delivery needs is found. | Water supply entity/utility Act, water and sanitation legislation, tariff regulations, service rules, State policies and other applicable binding instruments |
| UPD 3b | Implementation | (a) absence-based | Score 0 — No identifiable consideration of affordability or service access for economically vulnerable groups is found. / Score 0: No identifiable consideration of women’s access or service-delivery needs is found. / Score 0 if there is no identifiable equity/accessibility consideration. | Water supply entity's current water supply/sanitation plan; scheme/coverage documents; tariff or connection-concession orders; design/service standards. |
| UPD 4a | Law/Policy | (a) absence-based | Score 0: No specific legal provision addresses the mobility needs of economically vulnerable groups. / Score 0: No specific legal provision addressing women’s safety or mobility needs is found. | Transport authority/corporation Act, applicable transport legislation, rules, service regulations, fare policies and other binding policy instruments |
| UPD 4b | Implementation | (a) absence-based | Score 0: No identifiable consideration of affordability or service access for economically vulnerable groups is found. / Score 0: No identifiable consideration of women’s mobility or safety needs is found. | Transport Corporation's current transport/mobility plan; fare policy/concession orders; service design standards or specifications; annual report. |
| UPD 5a | Law/Policy | (a) absence-based | Score 0: No specific legal requirement is found. | Water supply entity/utility Act, water and sanitation legislation, service rules, State water policies, groundwater/source-protection provisions and other binding instruments |
| UPD 5b | Implementation | (a) absence-based | Score 0: No identifiable environmental sustainability consideration is found. | Water supply entity's current water supply/sanitation plan; source-protection or conservation programme documents; wastewater treatment/reuse scheme documents; annual report. |
| UPD 6a | Law/Policy | (a) absence-based | Score 0: No specific legal requirement requiring the Corporation to consider environmental sustainability in its planning, investment or service-delivery functions is found. | Transport authority/corporation Act, applicable transport legislation, rules, mobility/transport policies and other binding instruments |
| UPD 6b | Implementation | (a) absence-based | Score 0: No identifiable environmental sustainability measure is found. | Transport Corporation's fleet plan; route/network plan; environmental/sustainability policy; annual report. |
| DPG 1a | Law/policy | (b) condition-based | Score 0 if both Acts assign the same function with no distinction between them. / Score 0 if the assigned aspects overlap, or if the parastatal's aspect is not clearly specified in its Act. | Relevant Parastatal Act; State Municipal Act — record the specific provisions establishing devolution status and (where applicable) the functional carve-out. |
| DPG 1b | Law/Policy | (a) absence-based | Score 0 — The parastatal’s jurisdiction cannot be clearly established from the applicable legislation or subsequent legally valid notifications/orders. | Enabling Act, 12th Schedule mapping exercise |
| DPG 2a | Law/Policy | (a) absence-based | Score 0: No ULG representation on the governing board is provided for or found. | Composition clause of enabling Act; current board member list; Also check as per the parastatal website. |
| DPG 2b | Law/Policy | (a) absence-based | Score 0 for each component where no such requirement exists. | Plan/Budget preparation/Annual report preparation clause of the enabling Act of the relevant parastatal |
| DPG 3 | Implementation | (a) absence-based | Score 0 if no official website is found. | Live URL, screenshot/web-archive capture, date of check of the website of the relevant parastatal |
| DPG 4 | Law/Policy | (c) none stated | *(none: the methodology is only a note, "scoring ... has not been undertaken")* | *(empty in the bank)* |
| DPG 5a | Implementation | (a)+(b) mixed | Score 0: Budget cannot be found/accessed on the website., or the latest available budget is older than the permitted period. / Score 0 — Budget information is available only in a non-open or non-reusable format, including: | Website screenshots/archived URLs with date of access, for each document type |
| DPG 5b | Implementation | (a)+(b) mixed | Score 0 — Quarterly financial statements cannot be found/accessed on the website, or the latest available statements are older than the permitted period. / Score 0 — Quarterly financial information is available only in a non-open or non-reusable format, including: | Website screenshots/archived URLs with date of access, for each document type |
| DPG 5c | Implementation | (a)+(b) mixed | Score 0: The annual report cannot be found/accessed on the website, or the latest available report is older than the permitted period. / Score 0: The annual report is available only as a document or other non-structured format, including: | Website screenshots/archived URLs with date of access, for each document type |
| DPG 5d | Implementation | (a)+(b) mixed | Score 0: Data on civic works/projects and/or information on ongoing projects cannot be found/accessed on the website, or the latest available information is older than two years. / Score 0 — Information is available only in a non-structured or non-reusable format, such as: | Website screenshots/archived URLs with date of access, for each document type |
| DPG 5e | Implementation | (a)+(b) mixed | Score 0: Meeting Minutes cannot be found/accessed on the website or is older than the permitted period. / Record the FY/year/date of the latest information found in a separate evidence field even where the score is 0. / Score 0: Meeting Minutes is available but does not meet that standard (Scanned/image-only minutes; image gallery) | Website screenshots/archived URLs with date of access, for each document type |
| DPG 5f | Implementation | (a)+(b) mixed | Score 0:Score 0: If the parastatal's parent act/enabling legislation is not found on the website. / Score 0: Parastatal's parent act, allied rules, and government orders or notifications are available but do not meet that standard given above . | *(empty in the bank)* |
| DPG 5g | Implementation | (a)+(b) mixed | Score 0 if none are on the website. / Score 0 if each are only available non-searchable/non-readable format, such as an image-only organogram, scanned list or image-based directory/PIO details. | Website screenshots/archived URLs with date of access, for each document type |
| DPG 5h | Implementation | (a)+(b) mixed | Score 0 — Performance information cannot be found/accessed on the website, or the latest available information is older than the permitted period. / Score 0: Performance information is available only in a non-open or non-reusable format, including: | Website screenshots/archived URLs with date of access, for each document type |
| DPG 6 | Implementation | (a) absence-based | Score 0: Charter cannot be found/accessed on the website. | Website screenshots/archived URLs with date of access, for each document type |
| DPG 7a | Implementation | (c) none stated | *(none: 1.11 marks per component, "Where all 3 components are available, award the full score of 3.33"; nothing says when 0 is given)* | Relevant parastatal's official website Detailed evidence information provided in the methodology column (I 33) |
| DPG 7b | Implementation | (a)+(b) mixed | Score 0, if such portals are inaccessible, defunct or unavailable on the website. | *(empty in the bank)* |
| DPG 7c | Implementation | (a) absence-based | Score 0, if information in inaccessible or unavailable on the website. | *(empty in the bank)* |
| DPG 8a | Law/Policy | (a) absence-based | Score 0 if no applicable requirement is found. Record the legal provision, plan type, form of participation prescribed, and whether the provision uses mandatory or discretionary language. | Parastatal Act and rules; applicable T&CP Act; State Municipal Act. |
| DPG 8b | Implementation | (a) absence-based | Score 0, if there is no evidence for public consultations in the plan preperation process taking place. | Plan document; consultation reports; public notices; minutes/proceedings of consultations or hearings on the parastatal's official website; media reports. |
| SC 1 | Implementation (Numeric) | (a) absence-based | If budget data for at least 2 years is not available, score 0. | Annual budget of the last three financial years of the relevant parastatal. |
| SC 2 | Implementation (Numeric) | (a) absence-based | If budget data for at least 2 years is not available, score 0. | Latest annual budget and capital-expenditure accounts of the relevant parastatal; population figure with source. |
| SC 3 | Implementation (Numeric) | (a)+(b) mixed | Score 10 if the average variance is 15% or below; score 0 if it is above 15%. / If budget data for at least 2 years is not available, score 0. | Budget documents and audited accounts for the same financial year, compared side by side |
| SC 4a | Law/Policy | (a) absence-based | Score 0 if no provision for preparation of a annual financial statements or annual accounts is found. | Enabling act of the relevant parastatal |
| SC 4b | Implementation | (a) absence-based | Score 0 if no annual financial statements or annual accounts are publicly available online. | Website of the relevant parastatal |
| SC 5a | Law/Policy | (a) absence-based | Score 0 if no provision for preparation of internal audit reports is found. | Enabling act of the relevant parastatal |
| SC 5b | Implementation | (a) absence-based | Score 0: Neither is found. | Website of the relevant parastatal |
| SC 6a | Law/Policy | (a) absence-based | Score 0 if no provision for preparation of a annual budget within a specified time period is found. | *(empty in the bank)* |
| SC 6b | Implementation | (a) absence-based | Score 0 if there are no mandated timelines or if the annual budget is not publically available | *(empty in the bank)* |
| SC 7a | Law/Policy | (a) absence-based | Score 0 if no provision for preparation of a annual financial statements or annual accounts within a specified time period is found. | *(empty in the bank)* |
| SC 7b | Implementation | (a) absence-based | Score 0 if there are no mandated timelines or if the annual financial statements/annual accounts are not publically available. | *(empty in the bank)* |
| SC 8a | Law/Policy | (a) absence-based | Score 0 if no provision for preparation of a medium-term or long-term fiscal plan is found. | Enabling act of the relevant parastatal |
| SC 8b | Implementation | (a) absence-based | Score 0 if no medium-term or long-term fiscal plan is publicly available online. | Website of the relevant parastatal |
| SC 9 | Implementation | (a)+(b) mixed | Score 0: if only a Receipts and Payments Statement or other cash-based statement is available; the applicable accounting framework refers to or requires double-entry accounting, but the published financial statements do not demonstrate its use in practice; or | Parastatal website; latest available audited annual financial statements |
| SC 10 | Law/Policy | (b) condition-based | Score 0 if the law does not mandate a minimum tenure of at least two years. | Relevant Parastatal Act; rules governing appointment, tenure and removal of the executive authority/chief executive. |
| SC 11 | Implementation (Numeric) | (b) condition-based | Score 0 if more than 3 chief executives have served during the five-year period. | Newspaper reports, Gazette notifications of appointment/transfer and website of relevant parastatal |
| SC 12a | Implementation (Numeric) | (a) absence-based | If staffing data is not available, score 0. | Staffing records on the website/ RTI and/or formal data request with the parastatal/ annual report |
| SC 12b | Implementation (Numeric) | (c) none stated | *(none: score is relative to the best city; no zero rule)* | Staffing records on the website/ RTI and/or formal data request with the parastatal/ annual report |

Notes on the text itself [V]: DPG 6 says "Part A ... 5.0" but "Score 10"; DPG 7a says 1.11 per component but "Score 1.25" once; DPG 7c says "Score 3" with Max 3.33; UPD 1a and UPD 1b list bands to 10 with Max 5; DPG 7b and 7c contain "(?)". For Law/Policy questions the methodology often names more sources than the Evidence column does (for example DPG 2b names the Municipal Act, the Evidence column does not).

## 6. Conflicts: every rule on zero, absence, blank or "not found"

**Precedence today.** The text says the methodology wins: `shared-rules.md:54-57`, `shared-rules-city.md:44-47`, `scoring-methodology.md:7-9`, `score-question.md:62-65` (rule 14), and the first bullet of `upd.md`, `sc.md` and `dpg.md`. They say: skills, memory and "these rules" are help only; if one disagrees with the methodology, follow the methodology and add "CONFIRM: <file> says X, the methodology says Y" [V]. **But no file says that the task prompts' own zero rule is subordinate**, and the task prompt is the last text in the system prompt (`agent_setup.py:149-152`). In practice the specific zero rule wins [A]. Evidence: 101 of the 125 blank rows cite the rule; one note says it outright: *"CONFIRM: the methodology says to score 0 if data is unavailable, but the v2 rules require affirmative absence for a 0"* (Bhubaneswar, CRUT, SC 12a, Step 2 notes) and then follows the rule [V]. Only 7 of 414 Step 2 answers contain a "methodology says" CONFIRM, and none of the other 6 is about a zero [V].

| File:line | Sentence (shortened) | Can it override a methodology zero? |
|---|---|---|
| `prompts/answer-question.md:48-50` | "A rubric 0 needs AFFIRMATIVE ABSENCE: every relevant layer was in the Citation Sheet and read, no provision was found, and you list what you checked. Otherwise it is 'not found', never 0." | **Yes. This is the main conflict.** It is stricter than "0 if no provision is found". |
| `prompts/answer-city-question.md:47-49` | Same sentence (ULG category). | Yes (ULG category only). |
| `prompts/score-question.md:26-29` (rule 5) | "An input that would score 0 ... needs AFFIRMATIVE ABSENCE ... Otherwise leave it '': not found is not absent." | **Yes** (Step 3). |
| `skills/scoring-methodology.md:30-32` | "A rubric 0 (or a 'NO' input that scores 0) needs AFFIRMATIVE ABSENCE ... Otherwise ... leave the score/input blank." | **Yes** (attached to both Step 2 and Step 3). |
| `skills/scoring-methodology.md:40-41`, `score-question.md:33-34` (rule 7), `skills/sections/dpg.md:33-35` | Website evidence that could not be opened is "a verification limit, never a negative finding: never score it 0" / "score null, Confidence Low". | **Yes** for every website zero (DPG 3, 5a to 5h, 6, 7b, 7c, SC 4b, 5b, 6b, 7b, 8b). The methodology says "0 if cannot be found on the website". |
| `skills/sections/sc.md:26-27` | "'Not found' is not 'absent': a staffing or data question is not scored 0 without affirmative absence (Class R)." | **Yes, and it contradicts SC 12a directly** ("If staffing data is not available, score 0") and SC 1, 2, 3. |
| `prompts/shared-rules.md:36-37` | "'Blocked to automated tools' means a person may still open the page: ... never proof that the page is broken or absent." | Yes, for website zeros. |
| `prompts/shared-rules.md:3-4`, `shared-rules-city.md:4-5` | "An empty field with a stated reason is correct output. A plausible guess is a defect." | Indirect: it nudges toward blank. A methodology zero is not a guess, but the model may treat it as one. |
| `prompts/answer-question.md:5`, `answer-city-question.md:5` | "An honest blank beats a plausible fill." | Indirect, same as above. |
| `prompts/answer-question.md:51-54`, `answer-city-question.md:50-53` | "SCORE only if: the answer is sufficient, every rubric component is determined, the FIT CHECK passes, and no CONFIRM condition blocks it. ... Otherwise proposed_score = null ('SCORE-BLANK: ...')." | Yes, for part-based zeros (DPG 2b, DPG 5x, UPD 3a): one undetermined component blanks the whole score, even if the other components are clear zeros. |
| `prompts/answer-question.md:33-34`, `answer-city-question.md:32-33` | "Current-period question with only older evidence -> 'partial', no score." | Blocks a score when the methodology's own zero is "older than the permitted period" (DPG 5a to 5d, 5h, SC 4b, SC 8b). |
| `prompts/answer-question.md:64-67` | "'insufficient' - no source answers it, or the evidence is outdated, too general or only metadata." | Indirect and strong: "insufficient" is blanked by code (`base.py:338-339`) and gates Step 3 (`ai.py:350-353`). |
| `prompts/answer-question.md:69-81` (modes) | R, P, M and "Needs review": "no score". | Blocks a score for any question the model puts in class R/P/M (18 R and 2 M answers are "Insufficient Evidence"). |
| `prompts/score-question.md:21-25` (rule 4) and `:35-38` (rule 8) | "If the Citation Sheet doesn't let you decide an input, leave it '' ... If the evidence fits no band, leave the input '' and say 'RUBRIC-GAP'." | Indirect: a zero band that says "no evidence" can be read as "no band fits". |
| `skills/sections/upd.md:22-23` | "If the band depends on whether ... count as 'spatial and/or sectoral plans': score null + 'CONFIRM: plan-scope'." | Local to UPD 1a/1b/2: blank bias. |
| `skills/sections/sc.md:24-25` | Media-only evidence: "class at most A2, Confidence Low, score null." | Indirect for SC 11 (its Evidence column names newspaper reports). |
| `agents/question-scorer.md:21-23` | "If Step 2 found no evidence, or a check fails, the inputs are left blank for a person." | Describes the code gate (`ai.py:350-353`); blocks Step 3 whenever Step 2 blanks. |
| `prompts/shared-rules.md:86-91` | "If the evidence is insufficient, say so." | Weak. |
| `prompts/shared-rules.md:54-57`, `shared-rules-city.md:44-47` | "The Detailed Methodology ... is the rule." | **Supports the methodology.** It is the only precedence rule, and it is not tied to zero. |

No memory note (`agent_setup/memory/`) and no agent file other than the two above sets a zero rule [V]. `dpg.md:36-37` ("A scanned or unextractable PDF = 0 for the format half per the rubric") agrees with the methodology.

## 7. Checks in code

| Check | Exists? | File and function | Enforced in code, or only in a prompt? |
|---|---|---|---|
| (a) Methodology text reaches the model | **Step 2 and 3: yes. Step 1: no** (finder gets only the Evidence column; assessor gets nothing) | Step 2 `agents/sections/base.py:156-167` `_question_block`. Step 3 `scoring/template_scoring.py:145-198` `build_prompt`. Step 1 `agents/common.py:53-57` `question_digest`. | **Enforced in code** that it is sent. Nothing checks it was used. |
| (b) Answer's band or zero matches a methodology level (BAND check) | **Partly** | `methodology.py:32-62` `band_problem`, called at `base.py:354-357` (Step 2) and `template_scoring.py:307` (Step 3). Step 3 also: `template_scoring.py:414-452` `_typed_score` with `scoring/score_levels.py`. | **Code, but weak.** `band_problem` only adds a "CONFIRM" note: it checks that the band's leading number is one of the listed levels, or that a Part is named. It never changes or blocks a score, and it does not compare the score to the band. Step 3 does block a score that is not an allowed level. |
| (c) The methodology's zero condition was actually evaluated | **No** | Nothing parses or evaluates a zero condition. `score_levels.py` only reads the level numbers (0 among them) to build the allowed list. | **Prompt only** (and the prompt rule is stricter, see section 6). |
| (d) Sources named in the Evidence column were consulted before concluding absence | **No** | The nearest thing is the note "Citations reviewed: ..." (`base.py:360-361`), a log, not a check. | **Prompt only** (`answer-question.md:48-50`). Nothing maps the Evidence text to sources. |
| (e) A 0 is blocked when required sources are missing | **Blocked, but by a blanket rule, not by required sources** | `base.py:338-339`: status "Insufficient Evidence" sets the score to None. `base.py:221-230`: no usable source means no model call. `ai.py:350-353`: Step 3 not called. `template_scoring.py:348-358`: calculated rows are not written with missing inputs. | **Code** blocks *every* score (zero or not) when Step 2 has no evidence, whether or not the methodology defines zero as "not found". For a partial answer, a 0 passes code (`base.py:331-337` only clamps 0 to Max) and is blocked only by the prompt. |
| (f) Step 3 re-checks the Step 2 score against the methodology | **Not as such** | Step 3 is not given Step 2's numeric score (`phase2.py` `StepTwoAnswer` has no score field). The model scores again from methodology + source. `ai.py:366-387` `check_reply_evidence` re-checks the citation and quote. | **Code** re-checks the citation and quote only. No code compares Step 3's score to Step 2's or to the methodology (except the allowed-score list). |

Other code facts [V]: the answer's quote must appear word for word in the cited source (`base.py:279-290`); a score above Max is capped (`base.py:331-337`); a Class A2 with High confidence gets a note (`base.py:130-131`).

## 8. Real data check: human zero, AI blank

**Data used** [V]: merged people's workbooks `scoring/2027/merged/PARASTATAL_{UPD,SC,DPG}_human.xlsx` (scorer Neha, merged 17 Nov), the AI workbooks `scoring/2027/ai/PARASTATAL_*_AI.xlsx`, the Step 2 answers `outputs/Parastatal/cities/Bengaluru/answers/20261117-164004-1e7c/` and `.../Bhubaneswar/answers/20261117-153614-726f/`, and the Step 3 run logs `scoring/2027/ai/runs/PARASTATAL_*_20261117-182622.jsonl`. The human files are there; nothing is missing.

**Totals**

| | Bengaluru | Bhubaneswar | Both |
|---|---|---|---|
| Rows a person scored | 101 | 100 | 201 |
| People gave 0 | 54 | 73 | **127** |
| People 0 and AI blank | **52** | **73** | **125** |
| People 0 and AI also 0 | 1 | 0 | 1 |
| People 0 and AI scored above 0 | 1 | 0 | 1 |
| Share of "only people scored" rows that are zeros | 52 of 85 (61%) | 73 of 92 (79%) | 125 of 177 (71%) |

**Why the AI was blank on those 125** [V counts]:
- Step 2 status: Insufficient Evidence 93, Partially Answered 28, Human Verification Required 4.
- Step 3: not called ("Step 2 found no evidence") on 97; called on 28 (1 failed the quote check; of the other 27 the model's own comment says "absence not affirmed" for 20 and VERIFICATION-LIMIT for 7).
- Text in Step 2 or Step 3 notes: 101 cite the affirmative-absence rule or "a 0 is not allowed"; 40 say VERIFICATION-LIMIT; 22 say the Rules layer is missing from the sheet. Every one of the 125 has a SCORE-BLANK reason.

**Counts by methodology zero class** (the 125 rows) [V counts, class is [A]]:

| Zero class of the question | Rows | Share |
|---|---|---|
| (a) absence-based | **91** | 73% |
| (a)+(b) mixed | **29** | 23% |
| (b) condition-based | **5** (all SC 10) | 4% |
| (c) no zero stated | 0 | 0% |

**Was the methodology's zero condition met by what the Citation Sheet held? (proxy)** [A]. I checked whether the sources the Evidence column names were in the agency's usable Citation Sheet rows, using the finder's first tag: for a Law/Policy question, a parent Act row [ACT]; for an Implementation question, a website row. Of all 125 rows, the source was in the sheet for 78 and missing for 47. Of the 96 absence/mixed rows whose notes cite the absence rule, **62 had that source in the sheet** (the rule could have changed the result) and **34 did not** (the blank was correct, and the cause is Step 1). Among the 51 Law/Policy rows: the agency had a parent Act row in 21, all of them Bengaluru; **none of the 30 Bhubaneswar Law/Policy rows had one** (BDA, WATCO, CRUT). For the 74 Implementation rows, 57 had a homepage-level website row, but a website question usually needs a specific sub-page (charter, budget, minutes), which was often not saved.

**The 12 rows** (6 Bengaluru, 6 Bhubaneswar; 6 Law/Policy, 6 Implementation; absence, mixed and condition-based):

**1. Bengaluru · BWSSB · UPD 2a** (Law/Policy; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 if no such provision exists.
- Evidence / Source Requirement: Relevant Parastatal Act; applicable Town and Country Planning (T&CP) Act.
- Step 2: Insufficient Evidence, class A2, confidence Low, citation none. AI's blank reason: "the T&CP Act is not in the Sheet and the BWSSB Act's operative text was not fully read, so affirmative absence is not shown."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: Full operative text of the Bangalore Water Supply and Sewerage Act, 1964 as in force, its Rules and Regulations, and the Karnataka Town and Country Planning Act, 1961, including any provision requiring agencies or sectoral plans to con
- Human: score 0. Source: https://dpal.karnataka.gov.in/storage/pdf-files/29%20of%202021%20(E).pdf. Reason: "The BWSSB act does not include anything about aligning the schemes/plans with the city master plan. No mention of sectoral plans either in T&CP Act or Parastatal Act. Although the Section 14(4)of the GBA Act 2024 empowers GBA to supervise and coordinate the plans of public authorities connected with municipal activities in Greater Bengaluru Area, there is no specific mention of"
- Zero condition met by the Citation Sheet? Did the AI rule override it? PARTLY. The Act was in the sheet, but the T&CP Act (named in the Evidence column) was not. The zero condition could be tested only in part. The AI rule was applied, and a blank with the reason 'T&CP Act missing' was the safe result.

**2. Bengaluru · BMTC · SC 5a** (Law/Policy; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 if no provision for preparation of internal audit reports is found.
- Evidence / Source Requirement: Enabling act of the relevant parastatal
- Step 2: Partially Answered, class A2, confidence Low, citation BMTC-02. AI's blank reason: "affirmative absence not established because the Rules and Regulations are not in the sheet."
- Step 3: I left the score blank because absence cannot be shown. The RTC Act s.33 requires annual accounts and an external CAG audit. That is not an internal audit, so it does not earn 5 or 2.5. I found no provision in the Act for internal audit reports. I read the excerpts of BMTC-02 and relied on the Step 
- Human: score 0. Source: KSRTC rules, 1961. Reason: "No provision for preparation of internal audit reports is found. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? YES, THE METHODOLOGY'S ZERO WAS MET, AND THE AI RULE OVERRODE IT. The Evidence column names only the enabling Act. The Act (BMTC-02) was in the sheet and the AI itself wrote that it 'found no provision in the Act for internal audit reports'. It still left the score blank because 'Rules and Regulations are not in the sheet'.

**3. Bengaluru · BDA · DPG 2b** (Law/Policy; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 for each component where no such requirement exists.
- Evidence / Source Requirement: Plan/Budget preparation/Annual report preparation clause of the enabling Act of the relevant parastatal
- Step 2: Partially Answered, class A2, confidence Low, citation BDA-02. AI's blank reason: "affirmative absence not established, because the GBA Act was seen only in excerpts and the KMC Act is not in the sheet."
- Step 3: In the BDA Act text I read, estimates, audited accounts and reports go to the State Government or the Legislature. They do not go to the ULG, and the methodology does not count submission to the State only. I did not set any input to No. Affirmative absence needs the whole instrument stack to have b
- Human: score 0. Source: https://dpal.karnataka.gov.in/storage/pdf-files/acts%20alpha%20and%20dept%20wise%20acts/12%20of%201976%20(E).pdf. Reason: "[Migrated: the Yes/No parts were worked out from the old score (no part present); the old sheet did not record them. Please check.] The Commissioner to present the annual estimate of income and expenditure to the BDA (Sec.42) and the state government (44). There are no mentions of plans. Annual Reports - Submitted only to the State government, not the ULGs. Hence scored 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? MOSTLY YES, OVERRIDDEN. The BDA Act (the enabling Act in the Evidence column) was in the sheet. The AI read that budgets and reports go only to the State, which the methodology says does not count, so each component was a zero under the methodology. The AI still refused to set any input to 'No' because the GBA Act was seen only in excerpts and the Municipal Act was not in the sheet. (The methodology names the Municipal Act, the Evidence column does not: the two columns disagree.)

**4. Bengaluru · BMTC · DPG 8b** (Implementation; zero class: (a) absence-based)
- Methodology's zero condition: Score 0, if there is no evidence for public consultations in the plan preperation process taking place.
- Evidence / Source Requirement: Plan document; consultation reports; public notices; minutes/proceedings of consultations or hearings on the parastatal's official website; media reports.
- Step 2: Insufficient Evidence, class A2, confidence Low, citation none. AI's blank reason: "no practice evidence of plan consultation by BMTC is in the sheet, and absence has not been affirmatively shown."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: The latest BMTC plan or planning exercise, such as a business or development plan or the Comprehensive Mobility Plan input, together with any public notices, consultation reports, minutes or media reports, and the relevant pages of the
- Human: score 0. Source: https://citizenmatters.in/hsr-feeder-bus-service-in-bengaluru-last-mile-connectivity/. Reason: "No evidence of public consultation for BMTC bus service. Came across media reports for HSR Layout metro feeder bus service which was driven by public consultation organised by DULT."
- Zero condition met by the Citation Sheet? Did the AI rule override it? YES, ON THE SHEET'S CONTENTS, OVERRIDDEN. The zero is 'no evidence for public consultations'. Eight BMTC documents were reviewed and none showed consultation. The Evidence column also names public notices and minutes on the website, which were not saved, so the test is not complete.

**5. Bengaluru · BWSSB · SC 8b** (Implementation; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 if no medium-term or long-term fiscal plan is publicly available online.
- Evidence / Source Requirement: Website of the relevant parastatal
- Step 2: Insufficient Evidence, class A1, confidence Low, citation none. AI's blank reason: "no fiscal plan was found, but the website sections were not fully reviewed, so absence is not affirmed. This is a verification limit, not a negative finding. A reviewer should check the live site and capture a dated screenshot."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: A manual check of the BWSSB website (reports, budget, publications, tenders and downloads sections) for a dated medium/long-term fiscal or business plan. The published Vision 2050 document, if it exists, with its date.
- Human: score 0. Source: (none given). Reason: "No evidence of medium/ long term fiscal plan on the website. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? PARTLY. The zero is 'no fiscal plan publicly available online'. The sheet holds only homepage-level BWSSB pages, so the AI could not search the site. Its blank is a verification limit, and the right output is 'candidate 0: check the website'.

**6. Bengaluru · BDA · DPG 5b** (Implementation; zero class: (a)+(b) mixed)
- Methodology's zero condition: Score 0 — Quarterly financial statements cannot be found/accessed on the website, or the latest available statements are older than the permitted period. / Score 0 — Quarterly financial information is available only in a non-open or non-reusable format, including:
- Evidence / Source Requirement: Website screenshots/archived URLs with date of access, for each document type
- Step 2: Insufficient Evidence, class A1, confidence Low, citation none. AI's blank reason: "no website evidence in the Citation Sheet; absence not established. VERIFICATION-LIMIT."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: The BDA official website's financial or disclosure pages, with a dated screenshot or archived URL showing whether quarterly financial statements are published, their latest period, and their file format (CSV/XLSX versus PDF).
- Human: score 0. Source: 1. https://bdakarnataka.in/. Reason: "Part A and B- Quarterly financial reports cannot found on the BDA website. Hence, scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? NO, NOT TESTABLE. The sheet had no usable BDA website pages (the kbda.karnataka.gov.in links did not verify and bdakarnataka.in needs JavaScript). The blank is correct. This is a Step 1 gap, not a rule conflict.

**7. Bhubaneswar · WATCO · SC 10** (Law/Policy; zero class: (b) condition-based)
- Methodology's zero condition: Score 0 if the law does not mandate a minimum tenure of at least two years.
- Evidence / Source Requirement: Relevant Parastatal Act; rules governing appointment, tenure and removal of the executive authority/chief executive.
- Step 2: Insufficient Evidence, class A2, confidence Low, citation none. AI's blank reason: "no affirmative absence, because the Articles of Association and the constitution GO are not in the Citation Sheet."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: WATCO's Memorandum and Articles of Association, the Government of Odisha order or resolution constituting WATCO, and any HUD rules or appointment orders that set the MD/CEO's term and removal protection.
- Human: score 0. Source: https://rtiodisha.gov.in/Pages/printAllManual/office_id:23186/lang:. Reason: "Found no legal source mandating a fixed tenure for the chief executive officer. Currently being chaired by Principal Secretary to Government, Housing & Urban Development Department and the Managing Director (Er. Debabrata Mohanty) is an appointed Additional Chief Engineer. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? NO, NOT TESTABLE. The zero is condition-based ('the law does not mandate a minimum tenure of at least two years'). WATCO is a company and has only two usable rows. Its Articles of Association and constitution order are not in the sheet. The human scored 0 from an RTI manual page. Here the two sides reason differently from thin evidence.

**8. Bhubaneswar · CRUT · DPG 6** (Implementation; zero class: (a) absence-based)
- Methodology's zero condition: Score 0: Charter cannot be found/accessed on the website.
- Evidence / Source Requirement: Website screenshots/archived URLs with date of access, for each document type
- Step 2: Insufficient Evidence, class A1, confidence Low, citation none. AI's blank reason: "affirmative absence not established; the Publication and Sitemap pages were not read. VERIFICATION-LIMIT."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: Saved copies of the CRUT website's Publication page, Sitemap and any 'Citizen Charter' page or PDF, with the date of access.
- Human: score 0. Source: (none given). Reason: "Charter cannot be found/accessed online. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? PARTLY. The zero is 'Charter cannot be found/accessed on the website'. CRUT has a homepage and some pages in the sheet, but not the Publication or Sitemap pages where a charter would be. Verification limit.

**9. Bhubaneswar · BDA · SC 7b** (Implementation; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 if there are no mandated timelines or if the annual financial statements/annual accounts are not publically available.
- Evidence / Source Requirement: (empty in the bank)
- Step 2: Insufficient Evidence, class A2, confidence Low, citation none. AI's blank reason: "no affirmative absence and no evidence of a mandated timeline or of published statements."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: The ODA Act 1982 and ODA Rules 1983 provisions on annual accounts and audit, including any timeline. Also BDA's published audited annual accounts (balance sheet, income and expenditure account) with their approval date.
- Human: score 0. Source: (none given). Reason: "Audited annual accounts cannot be found/accessed on the BDA website. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? PARTLY. The zero has two halves: 'no mandated timelines' (needs the Act, which is not in the sheet) or 'accounts not publicly available' (the sheet has 3 [ACCOUNTS] rows, but whether they are audited annual accounts within two years is not stated). The Evidence column is empty in the bank.

**10. Bhubaneswar · CRUT · UPD 4a** (Law/Policy; zero class: (a) absence-based)
- Methodology's zero condition: Score 0: No specific legal provision addresses the mobility needs of economically vulnerable groups. / Score 0: No specific legal provision addressing women’s safety or mobility needs is found.
- Evidence / Source Requirement: Transport authority/corporation Act, applicable transport legislation, rules, service regulations, fare policies and other binding policy instruments
- Step 2: Insufficient Evidence, class A2, confidence Low, citation none. AI's blank reason: "no binding instrument on the urban poor or women was in the sheet, so absence is not affirmed."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: H&UD Notification No. 1919 of 19-01-2018 and Corrigendum No. 7387 of 19-03-2018. CRUT's MoA/AoA. The Odisha fare notification and concession orders. The Odisha Motor Vehicles Rules provisions on women's reserved seats and concessions.
- Human: score 0. Source: (none given). Reason: "Found no mandate to consider the needs of the urban poor or women. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? NO, NOT TESTABLE. The zero is 'no specific legal provision found'. The sheet has no binding instrument for CRUT (no notification, no MoA/AoA, no fare order). The blank is correct and the fix is in Step 1.

**11. Bhubaneswar · WATCO · DPG 8a** (Law/Policy; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 if no applicable requirement is found. Record the legal provision, plan type, form of participation prescribed, and whether the provision uses mandatory or discretionary language.
- Evidence / Source Requirement: Parastatal Act and rules; applicable T&CP Act; State Municipal Act.
- Step 2: Insufficient Evidence, class A2, confidence Low, citation none. AI's blank reason: "the Act, T&CP and Municipal Act layers are not in the Citation Sheet, so affirmative absence is not shown."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: The Odisha Development Authorities Act 1982 and its planning rules, the Orissa Municipal Corporation Act 2003, WATCO's Memorandum and Articles of Association, the government orders that set up WATCO, and any state water or sewerage pla
- Human: score 0. Source: https://urban.odisha.gov.in/sites/default/files/2026-09/22959.pdf. Reason: "WATCO is empowered to implement water supply projects alongside the BDA's town planning schemes. However, found no mandate for it to prepare plans or involve citizens in them. Hence, scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? NO, NOT TESTABLE. The Evidence column names the Act and rules, the T&CP Act and the Municipal Act. None of them is in WATCO's two usable rows. The human's 0 rests on a document outside the sheet.

**12. Bhubaneswar · BDA · SC 5a** (Law/Policy; zero class: (a) absence-based)
- Methodology's zero condition: Score 0 if no provision for preparation of internal audit reports is found.
- Evidence / Source Requirement: Enabling act of the relevant parastatal
- Step 2: Insufficient Evidence, class A1, confidence Low, citation none. AI's blank reason: "the enabling Act and rules are not in the Citation Sheet, so absence is not affirmed and a 0 cannot be given."
- Step 3: Step 2 found no evidence (Insufficient Evidence). Source needed: The full text of the Odisha Development Authorities Act, 1982, as in force on 31 Aug 2026, including its accounts and audit chapter. Also the ODA Rules, 1983 (or other rules on finance and accounts), checked for any internal audit requ
- Human: score 0. Source: 1. ODA Act, 1982 2. ODA Rules 1983 3. ODA Rules (Amendment) 2010. Reason: "No mandate for preparation of internal audit reports. Hence scoring 0."
- Zero condition met by the Citation Sheet? Did the AI rule override it? NO, NOT TESTABLE. The only source the Evidence column names (the enabling Act) is not in the sheet: the ODA Act 1982 was not collected. The human used the ODA Act, its 1983 Rules and 2010 amendment. Fix in Step 1.

**Reading of the 12** [A]: the zero condition was met on the required sources and the AI rule overrode it in **3** rows (2, 3, 4); it was only partly testable in **4** (1, 5, 8, 9); it could **not** be tested because the required source was not in the sheet in **5** (6, 7, 10, 11, 12). Applied to all rows (proxy): the rule may be the cause in up to about 62 of the 125, a missing source is the cause in about 47, and the rest are unclear [A].

## 9. Class (A1 / A2 / R / P / M) and Confidence

- **Where the class is set:** the model writes it at the start of its notes ("CLASS: ...; CONFIDENCE: ...; BAND: ..."), per `prompts/answer-question.md:95-99`. Code reads it in `agents/sections/base.py:88-132` (`parse_class_line`); the allowed values are in `models.py:18`. A value that is not allowed is left blank with a note. The only content check is "Class A2 is never High confidence" (`base.py:130-131`) [V].
- **What the prompt says A1 means** (`answer-question.md:69-81`): "A1 | Auto-researchable. A primary public source is directly reachable: statute, Gazette/GO, official policy PDF, CAG report, annual report, official dashboard. One explicit provision or record answers it. | Layer 1 (laws); published parts of Layer 2 | AI, verified by analyst | High (Medium if any interpretation); score per rubric". The header says "CLASS says where the answer lives. Pick the first mode that fits." [V]
- **Is A1 allowed when no source was found?** Yes. The prompt defines the class as where the answer lives, not whether it was found, and no code rejects A1 with no citation [V]. In the data, A1 is used 40 times on answers with no source, always with Low confidence, which differs from "High (Medium if any interpretation)" [V].

Latest Step 2 files (207 answer rows per city, including 39 "Not Applicable" each) [V]:

| Class + status | Bengaluru | Bhubaneswar | Both |
|---|---|---|---|
| **A1 with Insufficient Evidence** | 19 | 21 | **40** |
| **A2 with Insufficient Evidence** | 32 | 62 | **94** |
| R with Insufficient Evidence | 7 | 11 | 18 |
| M with Insufficient Evidence | 1 | 1 | 2 |
| All Insufficient Evidence | 59 | 95 | 154 |
| Insufficient Evidence with confidence other than Low | 0 | 0 | 0 |

Step 2's own proposed scores in the latest files: Bengaluru 22 above zero, **2 zero**, 183 blank; Bhubaneswar 7 above zero, **0 zero**, 200 blank [V].

## 10. Conclusion

**In plain words**

| | (a) Is the methodology and Evidence / Source Requirement **sent**? | (b) **Obeyed** by the model? | (c) **Enforced** by code? |
|---|---|---|---|
| **Step 1** (find and select sources) | Evidence text: yes. Methodology: **no**. Assessor: neither. | Cannot be told. No prompt line says "find what the Evidence column names". Coverage counts a source as covering a question when the finder tagged it, not when it meets the Evidence column. | **No.** Code keeps a source if it opens and the assessor accepts the claimed use. |
| **Step 2** (answer) | Both, word for word. | **Methodology bands: mostly. Methodology zero: no.** The prompt's affirmative-absence rule is applied instead (101 of 125 blank rows). The Evidence column is shown but never turned into a "must-read" list. | **Partly.** Code checks the quote, the BAND number (note only) and blanks every "Insufficient" answer. No code reads the zero condition or the Evidence sources. |
| **Step 3** (score) | Both, word for word, plus the template notes. | Same as Step 2: 27 of the 28 rows where the model ran came back blank because of absence or a verification limit. | **Partly.** Allowed scores, citation and quote are checked. The model is not called at all when Step 2 says "Insufficient Evidence" (97 of the 125 rows). |

**The finding in one line:** the system has no place where "the methodology's zero condition" is read, and one prompt rule that blocks zero whenever absence cannot be proved. Because 46 of 52 methodologies define zero, wholly or partly, as "not found", that rule cancels most zeros.

**Smallest changes, ranked.** Nothing here is implemented.

| # | Change | Effort | Risk |
|---|---|---|---|
| 1 | **Fix the zero rule in the prompts** so it follows the methodology. Replace the "needs AFFIRMATIVE ABSENCE ... never 0" sentences in `answer-question.md:48-50`, `answer-city-question.md:47-49`, `score-question.md:26-29`, `scoring-methodology.md:30-32` and `sc.md:26-27` with: "If the methodology gives a zero condition, apply it. If the zero is 'not found', score 0 when the sources the Evidence / Source Requirement names are in the Citation Sheet and you read them (list them); if one is missing, leave blank and say which." Also soften `scoring-methodology.md:40-41`, `score-question.md:33-34` and `dpg.md:33-35` the same way: an unopened website is a limit; a saved site with no such page is a zero. | **Small**: text in 5 to 8 files, then one trial run on a few questions. | **Medium.** The model may give false zeros where the sheet is thin. Do it together with #2. |
| 2 | **Code gate: allow a zero only when the required sources are present.** Add a small table for the 52 questions (question code to the source tags the Evidence column needs, for example UPD 1a: parent Act + T&CP Act; DPG 6: the charter or Publication page). In Step 2 `finalize` and Step 3, if the answer or score is 0 and a required tag is missing from the agency's usable rows, blank it with the reason "Missing: <tag>". | **Medium**: about 100 to 150 lines, the 52-row table (hand-made), tests. | **Low to medium.** It makes a false zero hard, but a wrong table could block a true zero. |
| 3 | **Step 1: send the methodology's "Check ..." line and a "must find" line per question** to the finder, and make the coverage check use the table from #2 (a question is covered only when its required tags have a verified source). Flag agencies missing a required source before Step 2 ("Needs Attention"). | **Small to medium** | **Low.** Costs more input tokens in Step 1 [A, about 20 to 30% on the finder's message]. It fixes the other half of the 125 rows (Bhubaneswar has no parent Act row for any agency). |
| 4 | **Show the zero condition to the model explicitly.** Add per question to the Step 2 and Step 3 message a line "ZERO CONDITION (from the methodology): <sentence>", taken from the table in section 5. | **Small** | **Low.** It removes any doubt about which sentence applies. |
| 5 | **Report "blank because absence not proved" as "candidate 0"** in the Step 3 comment and the compare workbook, with the missing source named, so people can confirm zeros in bulk. Today a blank looks the same as "no idea". | **Small** | **Low.** |
| 6 | **Clean the data (team task, no code):** fill the 8 empty Evidence / Source Requirements; fix the typos listed in section 5 (DPG 7a "1.25", DPG 6 "5.0", the "(?)" marks, UPD 1a/1b scale, DPG 7c "Score 3"); decide DPG 4. | **Small** | **Low.** |
| 7 | **Let Step 3 judge absence-based zeros itself** when the required sources are present, instead of stopping at Step 2's "Insufficient Evidence" (`ai.py:350-353`). | **Medium** | **Medium.** It adds model calls (cost [A]) and could widen the gap between Step 2 and Step 3. Not needed if #1 and #2 work. |

**Order I would take:** #6 and #5 (free), then #1 with #2 together, then #3. Expected effect [A]: of the 125 rows, up to about 62 could change (the rows where the required source is present). About 47 rows (34 of them among the rows that cite the rule) need a Step 1 fix (#3) first. Neither number is a promise.
