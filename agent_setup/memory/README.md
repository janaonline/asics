# Memory: context from the research team

Add Markdown (`.md`) files here to give the agents context they can't find on the web, for
example: "BWSSB's budget is published under Finance → Reports", "Since 2025 the ULG for
Bengaluru means the GBA city corporations", or "Ignore the old bwssb.org website".

**Where you put a file decides when it is used:**

| Folder | Used for |
|---|---|
| `general/` | every run |
| `cities/<city>.md` (or `cities/<city>/…`) | only that city, e.g. `cities/bengaluru.md` |
| `verticals/<vertical>/` | only that ASICS vertical; the current one is `parastatal` |

**Optional:** narrow a note further with a settings block at the top:

```
---
parastatals: [BWSSB]        # only these parastatals
sections: [DPG]             # only these question-bank sections
agents: [citation-builder]  # only these agents (see agent_setup/agents/)
steps: [1]                  # 1 = finding sources, 2 = answering
---
```

**Memory is guidance, not evidence.** Answers must still quote the Citation Sheet; if a note
disagrees with a source, the source wins and the conflict is mentioned. Every answer lists the
memory files it used. Files named `README.md`, and anything in `_archive/` or `_history/`, are
never used.

You can also add, edit and archive notes on the app's **Agent setup** page.
