# ASICS Parastatal Assessment

A tool for Janaagraha's **Annual Survey of India's City-Systems (ASICS)** parastatal assessment.
It works in two controlled steps:

1. **Step 1: Find parastatals and sources.** Give it a city. It finds the city's parastatals itself, checks each one's official website, and builds a **Citation Sheet** of official sources for the question bank.
2. **Your team reviews the Sources workbook.** You can untick parastatals or sources, and add sources you know about.
3. **Step 2: Answer questions.** Every answer uses **only** the reviewed Citation Sheet and names the **Citation ID** it relies on. It includes a verbatim quote, where to find it, and a saved copy of the page.

This README has two parts:

- **[For the research team](#for-the-research-team)**: using the app and reviewing results. No technical knowledge needed.
- **[For developers](#for-developers)**: setup, how it works, and how to extend it.

---

# For the research team

## Opening the app

Double-click **`Start ASICS.command`** (Mac) or **`Start ASICS.bat`** (Windows) in the project
folder. A black window opens, then the app opens in your web browser. **Keep the black window
open** while you work; close it when you're done.

> If you see "This computer isn't set up yet", ask your developer to follow
> [Setting up a new computer](#setting-up-a-new-computer).

The **Home** page shows the three steps and where each city is up to. To learn the app, tick **Practice with sample data** on Step 1. It uses two made-up
cities, costs nothing, takes seconds, and shows every step.

## The city register

The list of cities is one Excel file, `data/cities/ASICS_Cities_and_Parastatals.xlsx`. Open it
from the app's **City register** page.

- **Cities sheet:** one row per city: City, State, and City government (ULG). That's all the tool needs.
- **Parastatals sheet (optional):** add a parastatal here only if you want to be sure the agent includes it. The agent finds the rest itself.
- **Don't add website links.** The tool finds and checks every link itself.

After saving, press **Check again** on the City register page. Any mistakes are listed in
plain language, and a mistake in one city never stops the others.

## Step 1: Find parastatals and sources

1. Open **Step 1 · Find sources** in the sidebar, pick the cities and sections, and press **Start Step 1**.
2. For each city the agent:
   - **Finds the parastatals.** It researches the state portal, the urban development department, the city government's site and official Acts, then adds the register's parastatals.
   - **Checks each parastatal's official website.** Every candidate website gets a score out of 100, with the reasons listed. See [How the official website is checked](#how-the-official-website-is-checked).
3. **Review screen, once for all cities.** You see each parastatal: why it was included, its website and score, the law that created it, and its status. Untick any you don't want researched, then press **Continue**. Unticked ones stay in the Sources workbook, marked *Include? = No*.
4. The agent **builds the Citation Sheet** for each parastatal. It searches for official sources for the questions, then runs a second, targeted search for any question still without a source. Every link is opened and checked.

The result is one **Sources workbook** per city, in **City files**:

| Sheet | What it's for |
|---|---|
| **How to Use** | Instructions |
| **Needs Attention** | Problems to check, in plain language |
| **Parastatals** | Every parastatal: **Include?** (Yes/No), Found By (Agent or Your team), website and **Website Check** score with reasons, Act, status, and the Yes/No facts that decide which questions apply |
| **Citation Sheet** | Every source, with a **Citation ID** (e.g. `BWSSB-07`), link, saved copy, what it's useful for, Verification Status, Authority Score, and **Use for Answers?** (Yes/No) |
| **Coverage** | Which questions have a source, and which have none yet |

## Reviewing the Sources workbook

Open it from **City files** with **Open the Sources workbook in Excel**. Then:

- **Parastatals:** set **Include?** to No to leave one out. To add one, add a row with its ID, name and Type, and leave Found By empty.
- **Citation Sheet:** open each link, or its saved copy, and set **Use for Answers?** to No for anything unsuitable. Links that failed the check start as No. To add a source, add a row with Parastatal (an ID from the Parastatals sheet, or `All parastatals`), Source Title, Official URL and What This Source Is Useful For. Leave Citation ID empty; it is filled in automatically. Your links are opened and checked the same way as the agent's.
- **Coverage:** questions marked *No source yet* will be answered *Insufficient Evidence* unless you add a source.
- **Your Notes** columns are never overwritten.

Save and close the file when you're done. You can run Step 1 again at any time, for example
to look for new sources. It keeps your decisions, your rows and your notes, and saves the
previous version in a `history` folder first.

### While it runs

The **Current run** page says **"Working, nothing for you to do right now"** while the agent
works. The **Right now** table shows what each parastatal is doing, for example *"Checking
links: 6 of 14 done"*, and when it last changed. Building the Citation Sheet takes several
minutes per parastatal, and up to 4 are worked on at once.

When the agent needs you, the page shows an **Action needed** banner with **Continue**
buttons. That's the only time you need to do anything.

If nothing has changed in the **Updated** column for more than 20 minutes, tell your
developer. Slow websites and slow research calls are stopped automatically (after 1 minute
and 15 minutes respectively) and reported in **Needs Attention**, so a run shouldn't get stuck.

## Step 2: Answer questions

Open **Step 2 · Answer questions** in the sidebar, pick the cities, and press **Start Step 2**. For each city you can
see how many parastatals and citations are ready.

- Answers use **only** Citation Sheet rows marked *Use for Answers? = Yes*. There is no other research.
- Each answer names its **Citation ID**, quotes the source word for word, and says **Where to Find It**.
- If nothing in the Citation Sheet answers a question, the answer is *Insufficient Evidence*, and **Source Needed** says what kind of document would answer it. Add one to the Citation Sheet and run Step 2 again.

Each Step 2 run creates a new **answers workbook** for the city, in **City files**.

## Viewing results in the portal

You don't need to open Excel just to look. On **Home**, press **View** on a city, or open
**City files**, for these tabs:

| Tab | What you see |
|---|---|
| **Overview** | Parastatals, citations ready, questions with a source, and a chart of answer status per parastatal |
| **Parastatals** | Each parastatal with its website, Website Check score, Act and status |
| **Citation Sheet** | Every source, searchable and filterable. Click one to see its notes and saved text. |
| **Coverage** | Which questions have a source, per parastatal |
| **Answers** | Choose a run, filter, and click a question to see the answer, citation, where to find it, and the **quote highlighted in the saved source** |
| **Files** | Open or download the workbooks |

**Re-check links** shows its results on screen too, including earlier re-checks. The portal
only shows what's in the workbooks; to change anything, open the workbook in Excel.

## Reviewing the answers

| Sheet | What it's for |
|---|---|
| **How to Review** | Instructions, plus what every Status means |
| **Needs Attention** | Problems to fix, in plain language; *Must fix* items first |
| **Citation Sheet** | The list the answers were allowed to use |
| **Parastatal Scoring - &lt;City&gt;** (or **Scoring - &lt;City&gt;** for long names) | One row per parastatal and question |
| Technical Log | For your developer; ignore it |

For each answer:

1. **Citation ID** tells you which Citation Sheet row it relies on. Click the **Citation URL**.
2. Read **Where to Find It**, for example *"Page 12 of the PDF, under the heading 'Section 16. Plans'"*.
3. Press **Ctrl+F** (Windows) or **Cmd+F** (Mac) and paste the **Search Phrase** to find the **Evidence Excerpt**.
4. If the page has changed, click **Open saved copy**.
5. Choose **Agree**, **Disagree** or **Needs change** in **Reviewer Decision**, and add a comment.

Rows are coloured: **green** is answered, **amber** needs a person to look, **red** means no evidence, and **grey** is not applicable.

## How the official website is checked

Each candidate website is opened and scored. The Website Check column lists every point:

| Signal | Points |
|---|---|
| Government web address (gov.in / nic.in) | +40 |
| Linked from other government websites | +20 for one, +30 for two or more |
| Opens properly and shows real content | +10 |
| Says it is run by the government, or is hosted by NIC | +10 |
| Lists a government email address (also written as `name[at]dept[dot]gov[dot]in`) | +10 |
| Has Right to Information (RTI) / PIO details | +5 |
| Its social media account is also linked from a government page | +5 |
| Its name or short name is in the web address or page title | +5 |
| A directory, Wikipedia, blog or social media page | always 0 |

**70+ = Official. 50–69 = Probably official**: used, but flagged for you to confirm. **Below 50
= Not confirmed**: not used as the official website, but sources are still researched from
other official sites. A website that doesn't open scores at most 49, but a gov.in / nic.in
address with the parastatal's own name is still treated as **Probably official**, and flagged
for you to open and confirm (many government sites are slow or don't open in the automatic
check).

## How links are checked

1. **Only links found by a web search, or added by your team, are used.** A link the AI writes from memory or pieces together is thrown away.
2. **Each exact link is opened separately**, the way a browser would, without changing it. It must show real, readable content. An error page, a login or captcha page, a data feed, or an India Code page showing only a summary of an Act doesn't count.
3. **Anything uncertain goes to a person.** Pages that need JavaScript, scanned PDFs and links that jump to another website are marked *Human Verification Required*, scored 0, and start as *Use for Answers? = No*.
4. **A copy of every page that passes is saved**, and every quote is matched against it word for word.

## Giving the agents more context (Team memory)

Some things the agents can't find on the web: where a parastatal hides its budget, a recent
renaming, a local term, a website to ignore. Add these as **notes** on the app's **Agent
setup** page (Team memory tab), or as `.md` files in `agent_setup/memory/`:

- **General:** used in every run.
- **One city:** used only when that city runs.
- **One vertical:** used only for that ASICS vertical. The current one is **parastatal**; add a new vertical (e.g. Mobility) when that work starts.

You can narrow a note to some parastatals, sections, agents or steps. Notes are **guidance,
not evidence**: answers still quote the Citation Sheet, and each answer lists the notes it used
in **Team Context Used**. Saving keeps the previous version, and archiving removes a note from
use without deleting it. The **Preview** tab shows exactly which notes an agent would receive.

## Checking links again later

Open **Re-check links**, pick a Sources or answers workbook, and press **Re-check now**. You get
a copy with **Link Still Opens?** and **Quote Still on Page?** columns. Your original is not
changed.

---

# For developers

## Setting up a new computer

1. Install [uv](https://docs.astral.sh/uv/). On a Mac: `brew install uv`.
2. In the project folder:

   ```bash
   uv sync
   ```

   ```bash
   cp .env.example .env
   ```

   Then set `ANTHROPIC_API_KEY` in `.env`.
3. Run the tests (offline, free):

   ```bash
   uv run pytest
   ```

4. Double-click `Start ASICS.command` to test the launcher. The first time, macOS may need right-click → **Open**.

The app only accepts connections from this computer (`.streamlit/config.toml`), because it
uses the API key.

## Other ways to run it

The app directly:

```bash
uv run streamlit run app.py
```

Step 1 for a city from the terminal (repeat `--city`, or use `--all-cities`):

```bash
uv run python scripts/run_pipeline.py --step sources --city Bengaluru
```

Step 2 from the terminal:

```bash
uv run python scripts/run_pipeline.py --step answers --city Bengaluru --pillar DPG
```

A free check of the question bank and register for every city:

```bash
uv run python scripts/run_pipeline.py --step sources --all-cities --checks-only
```

Re-check a workbook's links:

```bash
uv run python scripts/recheck_links.py "outputs/cities/Bengaluru/ASICS_Bengaluru_Sources.xlsx"
```

LangGraph Studio, with graphs `step1_sources` and `step2_answers`:

```bash
uv run langgraph dev
```

## How it works

```mermaid
flowchart TD
    subgraph S1["Step 1: sources_master.py"]
        IC1[initial_checks] --> PD[parastatal_discovery<br/><i>discover → profile × parastatal<br/>(website trust check)</i>]
        PD --> CS{{confirm_scope<br/><i>human review</i>}}
        CS --> LA[links_agent × parastatal<br/><i>re-test → research → fill gaps</i>]
        LA --> FS[finalize_sources<br/><i>QA · Sources workbook</i>]
    end
    FS --> SW[(Sources workbook<br/>reviewed and edited by the team)]
    SW --> IC2
    subgraph S2["Step 2: answers_master.py"]
        IC2[initial_checks] --> PC[prepare_citations<br/><i>check team-added rows</i>]
        PC --> ANS[answer_UPD / answer_DPG / answer_SC / answer_GENERIC<br/><i>× parastatal × question, Citation Sheet only</i>]
        ANS --> FA[finalize_answers<br/><i>roll-ups · QA · answers workbook</i>]
    end
```

- **Two master agents,** [agents/sources_master.py](src/asics_agent/agents/sources_master.py) and [agents/answers_master.py](src/asics_agent/agents/answers_master.py), handle one city each and route between phases with plain Python.
- **The Excel handoff** is [sources_workbook.py](src/asics_agent/sources_workbook.py). It reads, writes and merges the Sources workbook, keeping the team's decisions, rows, notes and Citation IDs across re-runs.
- **Several cities** run through `BatchRun` in [runner.py](src/asics_agent/runner.py), one after another. Step 1 has a single review for all cities, and the app and CLI both use it.
- **Files** go to `outputs/cities/<City>/`: the Sources workbook, `evidence/` (saved copies and text, shared by both steps), `history/`, `answers/<run>/` and `checks/`. Batch indexes go to `outputs/batches/<id>/`.

| Sub-agent | File | What it does |
|---|---|---|
| Initial checks | [initial_checks.py](src/asics_agent/agents/initial_checks.py) | Loads the question bank, the register and the city's Sources workbook |
| Parastatal discovery | [parastatal_discovery.py](src/asics_agent/agents/parastatal_discovery.py) | Finds parastatals (merged with the team's), profiles each in parallel, rates candidate websites |
| Website trust check | [links/trust.py](src/asics_agent/links/trust.py) | The scoring table above, computed in code from the page, the fetched government pages ("backlinks") and the access check |
| Links agent | [links_builder.py](src/asics_agent/agents/links_builder.py) | Re-tests earlier rows, researches sources, then a gap-filling pass for uncovered questions |
| Section answer agents | [sections/](src/asics_agent/agents/sections/) | Answer from the Citation Sheet only, citing a Citation ID; the quote is verified against the saved page |
| Roll-up + final QA | [rollup.py](src/asics_agent/agents/rollup.py), [final_qa.py](src/asics_agent/agents/final_qa.py) | Sum MQs where the methodology says so; `qa_sources` / `qa_answers` checklists |

### Agents, prompts, skills and memory: `agent_setup/`

Everything the model is told lives in [agent_setup/](agent_setup/), described in
[agent_setup/README.md](agent_setup/README.md). [agent_setup.py](src/asics_agent/agent_setup.py)
reads it:

- `call_json(services, "<agent>", …)` in [llm.py](src/asics_agent/llm.py) loads `agent_setup/agents/<agent>.md` and builds the system prompt (shared rules + skills + task prompt). It binds web tools only if `web_research: true`, and passes the agent's `effort`.
- Memory notes matching the call's `MemoryScope` (city, parastatals, sections, agent, step) are added at the top of the message; `scope.used` records them. The size limit is `ASICS_MEMORY_MAX_CHARS`, with the most specific notes kept first.
- Initial checks validate the folder (missing prompts or skills, broken settings blocks, notes for unknown cities). Each run's summary records `agent_setup_fingerprint`.

### Configuring LangGraph

**Graphs.** Two graphs are registered in `langgraph.json`: `step1_sources` and `step2_answers`.
Open them with `uv run langgraph dev`; LangGraph Studio shows every node, sub-graph and
parallel branch. Each graph is a `StateGraph` over `MasterState`
([agents/state.py](src/asics_agent/agents/state.py)), built by `build_sources_graph` and
`build_answers_graph`, using:

- sub-graphs as nodes: discovery, the links agent, one answer agent per section;
- `Send` to fan out per parastatal, and per parastatal × question;
- `interrupt()` for the review pause, with a checkpointer in [runner.py](src/asics_agent/runner.py);
- `stream_mode=["updates", "custom"]` for live progress.

**Run options (`context_schema`).** Both graphs declare
[`RunOptions`](src/asics_agent/run_options.py) as run context: `model`, `effort`,
`web_search_max_uses`, `max_tool_calls` and `memory_max_chars`.

- **Where to set them:** Studio shows them as a form per run. The CLI takes `--model`, `--effort`, `--web-searches` and `--max-tool-calls`. The app has **Advanced options** on the Start page.
- **Precedence:** a run's `effort`, `web_search_max_uses` and `max_tool_calls` override every agent's own setting. A run's `model` applies only to agents that don't name their own.
- **In code:** read them with `current_options()`.

**Agents and their tool loop.** Every model call goes through `call_json(services, "<agent>", …)`
in [llm.py](src/asics_agent/llm.py), which builds the agent from its file in
`agent_setup/agents/` and runs it as a small LangGraph graph:

```
model ──(our tool calls)──▶ tools (ToolNode) ──▶ model ──(final JSON)──▶ end
  ▲ └──(server tools paused the turn)──┘           └─▶ over_limit, after max_tool_calls
```

- **Server tools** (`web_search`, `web_fetch`) run inside the model call.
- **Our tools** run in LangGraph's `ToolNode`, so every call is a visible step in Studio, appears as live progress, and is listed in the Technical Log (and in an answer's Notes as "Looked further with: …").

**Adding a tool:**
1. Write `src/asics_agent/tools/<name>.py` with an `Args` Pydantic model and `register(ClientTool(name=…, args=Args, run=fn))`. `fn(ctx, **args) -> str` gets a `ToolContext` that holds only what that call may see: the run, the allowed URLs, and the Citation Sheet rows.
2. Write `agent_setup/tools/<name>.md`; its body is the description the model sees.
3. List it under an agent's `tools:`. The setup check catches unknown tools, bad options, both `allowed_domains` and `blocked_domains`, and web tools on Step 2 agents.

**Model per agent:** set `model:` in an agent's file; `Services.llm_for()` creates and reuses
one client per model.

### Where the rules are enforced

The original rules are in [docs/source_prompts/phase2_citations_and_answers.md](docs/source_prompts/phase2_citations_and_answers.md).
They're given to the model in [agent_setup/prompts/](agent_setup/prompts/) **and** enforced in code:

| Rule | Enforced by |
|---|---|
| A URL is used only if a tool returned it verbatim, or the team added it | [links/registry.py](src/asics_agent/links/registry.py); `qa_sources` |
| Human accessibility test, including India Code | [links/accessibility.py](src/asics_agent/links/accessibility.py) |
| Authority-score caps | [agents/common.py](src/asics_agent/agents/common.py): unverified sources get 0, non-government domains are capped at 5 |
| **Answers use only the Citation Sheet** | Step 2 agents can't have web tools (setup check); `answer_from_citations` and the `read_citation` / `search_citation_sheet` tools receive only in-use, verified rows; an answer citing any other ID becomes *Human Verification Required*; `qa_answers` re-checks |
| Links proposed by the citation builder were opened | `check_link` runs the same accessibility test during research, and refuses URLs no tool returned |
| Traceable quote | The quote must appear verbatim in the cited row's saved text; `locate_quote` finds its page and heading |
| Status and Notes on every row | `finalize` in `sections/base.py`; `qa_answers` |
| Preserve the workbook | [workbook.py](src/asics_agent/workbook.py) updates rows in place and never overwrites Reviewer or Your Notes columns |

The source prompt's "research an external source when the Citation Sheet is insufficient" is
now done **in Step 1** (the gap-filling pass), so that Step 2 is fully controlled by the
reviewed list.

### Messages: team vs developer

Every `Issue` has an `audience`. **`team`** messages are plain language (*what we found + what
to do*) and appear in the app and on **Needs Attention**. **`developer`** messages go only to
the **Technical Log**.

## Project layout

```
.
├── app.py                          # the research team's app (Streamlit)
├── ui.py  assets/                  # branding: ASICS header, styles, Janaagraha logo
├── Start ASICS.command / .bat      # double-click launchers
├── data/
│   ├── question_banks/Parastatal_ASICS_Question_Bank.xlsx
│   └── cities/ASICS_Cities_and_Parastatals.xlsx   # the city register (team-owned)
├── agent_setup/                    # agents, prompts, skills, team memory (Markdown)
├── agent_setup_page.py             # the app's Agent setup page
├── city_view_page.py               # the app's City files view (read-only)
├── docs/source_prompts/            # the original prompt the rules come from
├── scripts/  run_pipeline.py  recheck_links.py  create_city_register.py
├── src/asics_agent/
│   ├── agents/
│   │   ├── sources_master.py  answers_master.py  # the two master agents
│   │   ├── initial_checks.py  parastatal_discovery.py  links_builder.py
│   │   ├── sections/           # answer agent per section (base.py; sc.py adds a code check)
│   │   ├── rollup.py  final_qa.py  common.py  state.py
│   ├── links/                  # registry, accessibility, trust, text + quote location, SQLite
│   ├── sources_workbook.py     # the Step 1 → Step 2 handoff
│   ├── workbook.py             # answers workbook, index, checks report
│   ├── cities.py  runner.py  reporting.py  recheck.py  practice.py
│   ├── agent_setup.py          # reads agent_setup/: agents, prompts, skills, memory
│   ├── tools/                  # our own tools (check_link, read_citation, …)
│   ├── run_options.py          # per-run options (LangGraph context_schema)
│   └── applicability.py  question_bank.py  llm.py  services.py  models.py  config.py  progress.py
└── tests/                      # offline tests (practice mode)
```

## Adding a new section (e.g. a new pillar in the question bank)

A **section** is a part of the question bank, identified by the prefix of its question IDs
(UPD, DPG, SC). This is different from an ASICS **vertical** such as Parastatal or Mobility,
which is a whole assessment area with its own memory folder.

1. Add the questions to the question bank under a section header ending in the code, e.g. `(ELPR)`.
2. Add `agent_setup/skills/sections/elpr.md`:

   ```markdown
   ---
   name: ELPR
   title: Empowered & Legitimate Political Representation
   evidence_hints: board members elected councillors nominated chairperson notification
   ---
   - Board composition: name the section of the Act that sets out membership and say how
     many members are elected representatives.
   ```

Step 2 then gets an `answer_ELPR` agent automatically, and its questions are answered with
that guidance. Step 1 needs no change. Python is needed only for code-level checks:

| Need | How |
|---|---|
| Section instructions | the body of `skills/sections/<code>.md` |
| Better passage selection from long Acts or PDFs | `evidence_hints` in its settings block |
| Check or adjust each answer in code | a module in `src/asics_agent/agents/sections/` calling `register(SectionSpec(code="ELPR", postprocess=fn))`. See `require_figures` in [sc.py](src/asics_agent/agents/sections/sc.py) |
| A completely different workflow | `SectionSpec(build=fn)`, which receives an `AnswerTask` whose `citation_sources` are the only sources it may use |

## Adding a new ASICS vertical (e.g. Mobility)

- **Memory:** add a vertical on the **Agent setup** page (or a folder `agent_setup/memory/verticals/<name>/`), and set `ASICS_VERTICAL=<name>` for its runs.
- **Question bank:** a new vertical will usually have its own question bank and unit of assessment, so point `ASICS_QUESTION_BANK` at it.
- **Workflow:** if the unit isn't a parastatal (e.g. the city itself), the discovery step needs a developer to adapt it.

## Other common changes

- **Look and branding:**
  - Colours and font are in `.streamlit/config.toml` (`[theme]`). The ink colour comes from the Janaagraha logo; set `primaryColor` and `linkColor` to official brand colours if you have them.
  - The logo is `assets/janaagraha-logo.svg`.
  - The ASICS page header and the small shared styles are in [ui.py](ui.py).

- **New city:** the team adds a row to the city register.
- **New parastatal type:** add it to `TYPES` in [cities.py](src/asics_agent/cities.py) and give it a rule in [applicability.py](src/asics_agent/applicability.py).
- **Website scoring:** the weights and bands are at the top of [links/trust.py](src/asics_agent/links/trust.py).
- **Prompts, skills, agents:** `agent_setup/` (see [agent_setup/README.md](agent_setup/README.md)). `prompts/shared-rules.md` goes to every agent.
- **Settings:** `.env`; see `.env.example`.

## Limitations

- **The accessibility test uses plain HTTP requests.** JavaScript-only pages end up as *Human Verification Required*.
- **Backlinks come from government pages the agent fetched during research,** not from a full web-wide backlink index. Official social handles are matched only when a government page links to the same handle.
- **Time limits:** each web page download is limited to 60 seconds and 30 MB (`links/accessibility.py`), and each Claude call to `ASICS_LLM_CALL_TIMEOUT` seconds (default 900). These exist because httpx's timeout applies per network read, so a slowly trickling server once froze a whole run. Live progress comes from `progress.report()` through LangGraph's `custom` stream mode.
- **A run in progress lives in the app's memory.** Closing the black window mid-run loses that run, but files already written are kept.
- **Sheet names:** Excel limits them to 31 characters, so long city names get "Scoring - &lt;City&gt;".
- **Question bank data issues** (e.g. UPD 1a and 1b score out of 10 but have a max of 5) show up in **Needs Attention**.

## Development

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run ruff format .
```
