# Agent setup

Everything that shapes what the AI does, in plain Markdown. The code reads these files on
every call, so changes apply to the next run. No code changes are needed.

## Map

| Agent (`agents/`) | Step | Prompt (`prompts/`) | Skills (`skills/`) | Tools (`tools/`) |
|---|---|---|---|---|
| Parastatal discovery | 1 | `discover-parastatals` | government-websites | web_search, web_fetch |
| Website profiler | 1 | `parastatal-profile` | government-websites, india-code-and-acts | web_search, web_fetch |
| Citation builder | 1 | `find-sources` | government-websites, india-code-and-acts | web_search (no Wikipedia/directories), web_fetch, **check_link** |
| Source assessor | 1 | `assess-source` | india-code-and-acts | none |
| Answer writer | 2 | `answer-question` | scoring-methodology, india-code-and-acts, + the question's section | **read_citation**, **search_citation_sheet**, **lookup_question** (no web) |
| Question bank reviewer | checks | `bank-review` | scoring-methodology | none |

Every agent also receives `prompts/shared-rules.md` (the URL, verification and evidence rules)
and the **memory** notes that match its run.

**What an agent receives, in order:**
1. Shared rules.
2. Its skills.
3. Its task prompt.
4. In the message: the matching team memory, then the task input.

It may then call the tools in its settings, up to `max_tool_calls`. The app's **Agent setup →
Preview** shows the exact text.

## An agent's settings

```yaml
---
name: citation-builder
step: 1
prompt: find-sources                      # prompts/find-sources.md
skills: [government-websites, india-code-and-acts]
tools:                                    # exactly the tools this agent may call
  web_search: {max_uses: 8, blocked_domains: [wikipedia.org]}   # or allowed_domains, not both
  web_fetch: {max_uses: 8}
  check_link: {}
max_tool_calls: 20                        # our own tools (check_link…) per call
model: claude-sonnet-5-5                  # optional; default is the app's model
effort: high                              # low | medium | high | xhigh | max
---
```

Step 2 agents can't be given `web_search` or `web_fetch`: the setup check refuses it, because
answers must come only from the Citation Sheet.

## Folders

| Folder | What | Who edits |
|---|---|---|
| `agents/` | One file per agent. The settings block at the top (prompt, skills, web_research, effort) is read by the code; the text below describes the agent. | Developer |
| `prompts/` | Task instructions. `shared-rules.md` holds the evidence and URL rules. | Developer, reviewed |
| `skills/` | Reusable know-how, attached to agents in their settings. | Research lead with a developer |
| `tools/` | One page per tool. Its text is exactly the description the model sees, and the settings block says whether Anthropic runs it (server) or we do (client). | Developer |
| `skills/sections/` | Guidance per question-bank section (UPD, DPG, SC). A new section's file is picked up automatically, and its questions get their own answer agent. | Research lead with a developer |
| `memory/` | Context from the research team. See `memory/README.md`. | Anyone on the research team, here or in the app |

## Memory, in short

- **`memory/general/`:** used in every run.
- **`memory/cities/<city>.md`** or **`memory/cities/<city>/…`:** used only for that city.
- **`memory/verticals/<vertical>/`:** used only for that ASICS vertical. The current one is `parastatal` (setting `ASICS_VERTICAL`); add folders like `mobility/` when that work starts.
- **Narrowing a note:** a settings block at the top can limit it to some parastatals, sections, agents or steps.
- **Guidance, not evidence:** answers must still quote the Citation Sheet. Every answer lists the notes it used (the **Team Context Used** column), and each run records a fingerprint of this whole folder in its summary.
