"""The app's "Agent setup" page: the team's memory notes (add, edit, archive), new
verticals, and a read-only view of the agents, prompts and skills in agent_setup/."""

from pathlib import Path

import pandas as pd
import streamlit as st

from asics_agent.agent_setup import (
    MemoryScope,
    add_vertical,
    archive_note,
    list_notes,
    load_agents,
    memory_block,
    note_path,
    note_with_settings,
    save_note,
    section_codes,
    select_notes,
    split_front_matter,
    system_prompt,
    validate,
    verticals,
)

SCOPE_LABELS = {"general": "General (every run)", "city": "One city", "vertical": "One vertical"}


def render(settings, register, open_file, show_issue, question_bank):
    root: Path = settings.agent_setup_dir
    from ui import header

    header(
        "Agent setup",
        "What the agents are told: add context under Team memory; the other "
        "tabs show each agent's instructions, tools and skills.",
        "Settings",
    )
    if st.button("Open the agent_setup folder", icon=":material/folder_open:"):
        open_file(root)
    memory_tab, preview_tab, agents_tab, check_tab = st.tabs(
        ["Team memory", "Preview what an agent sees", "Agents, prompts & skills", "Setup check"]
    )
    configs, _ = register()
    with memory_tab:
        memory_editor(root, settings, configs)
    with preview_tab:
        preview(root, settings, configs)
    with agents_tab:
        agents_view(root)
    with check_tab:
        issues = validate(
            root,
            [c.name for c in configs.values()],
            settings.vertical,
            {q.pillar for q in question_bank().values()},
        )
        if not issues:
            st.success("No problems found in the agent setup.")
        for issue in issues:
            show_issue(issue)


def memory_editor(root: Path, settings, configs):
    st.markdown(
        "Notes here give the agents context they can't find on the web, for example "
        '*"BWSSB\'s budget is under Finance → Reports"* or *"since 2025 the ULG is the GBA '
        'city corporations"*. **They are guidance, not evidence**: answers must still quote '
        "the Citation Sheet, and every answer lists the notes it used."
    )
    notes, problems = list_notes(root)
    for issue in problems:
        st.warning(issue.message)

    with st.expander("Add a note", icon=":material/add:", expanded=not notes):
        add_note_form(root, settings, configs)
    with st.expander("Add a new vertical", icon=":material/create_new_folder:"):
        st.caption(
            f"The current vertical is **{settings.vertical}**. Add a folder for another "
            "ASICS vertical (e.g. Mobility) when its work starts; its notes are used "
            "only in that vertical's runs."
        )
        name = st.text_input("Vertical name", key="new-vertical", placeholder="e.g. Mobility")
        if st.button("Add vertical", disabled=not name.strip()):
            folder = add_vertical(root, name.strip())
            st.success(f"Added memory/verticals/{folder.name}/")
            st.rerun()

    groups = {"general": [], "city": [], "vertical": []}
    for note in notes:
        groups[note.scope].append(note)
    for scope, label in [("general", "General"), ("city", "Cities"), ("vertical", "Verticals")]:
        st.subheader(f"{label} ({len(groups[scope])})")
        if not groups[scope]:
            st.caption("No notes yet.")
        for note in groups[scope]:
            note_card(root, note, settings)


def add_note_form(root: Path, settings, configs):
    scope = st.radio(
        "Who is this note for?",
        list(SCOPE_LABELS),
        format_func=SCOPE_LABELS.get,
        horizontal=True,
        key="new-scope",
    )
    target = ""
    if scope == "city":
        target = st.selectbox("City", [c.name for c in configs.values()], key="new-city")
    elif scope == "vertical":
        target = st.selectbox("Vertical", verticals(root, settings.vertical), key="new-vert")
    title = st.text_input(
        "Title", placeholder="e.g. Where BWSSB publishes its budget", key="new-title"
    )
    text = st.text_area(
        "Note", height=180, key="new-text", placeholder="Write the context in plain language."
    )
    with st.expander("Only for some parastatals, sections or agents (optional)"):
        parastatals = st.text_input(
            "Parastatal IDs, comma separated", key="new-p", placeholder="e.g. BWSSB, BMTC"
        )
        sections = st.multiselect("Sections", list(section_codes(root)), key="new-s")
        agents, _ = load_agents(root)
        chosen_agents = st.multiselect(
            "Agents", list(agents), key="new-a", format_func=lambda a: agents[a].title
        )
        steps = st.multiselect(
            "Steps",
            [1, 2],
            key="new-steps",
            format_func={1: "Step 1: finding sources", 2: "Step 2: answering"}.get,
        )
    if st.button(
        "Save note",
        type="primary",
        disabled=not (title.strip() and text.strip()),
        icon=":material/save:",
    ):
        path = note_path(root, scope, title, target)
        if path.exists():
            st.error(
                f"A note called '{title}' already exists there. Edit it below, or choose "
                "another title."
            )
            return
        body = f"# {title.strip()}\n\n{text.strip()}"
        settings_block = {
            "parastatals": [p.strip().upper() for p in parastatals.split(",") if p.strip()],
            "sections": sections,
            "agents": chosen_agents,
            "steps": steps,
        }
        save_note(root, path, note_with_settings(body, settings_block))
        st.success(f"Saved memory/{path.relative_to(root / 'memory').as_posix()}")
        st.rerun()


def note_card(root: Path, note, settings):
    path = root / "memory" / note.path
    where = {
        "general": "every run",
        "city": f"city: {note.target}",
        "vertical": f"vertical: {note.target}",
    }[note.scope]
    unused = note.scope == "vertical" and note.target != settings.vertical.lower()
    with st.expander(
        f"{note.title}  ·  {where}" + ("  (not used in this vertical)" if unused else ""),
        icon=":material/description:",
    ):
        st.caption(f"memory/{note.path}")
        filters = {k: v for k, v in note.filters.items() if k != "title"}
        if filters:
            st.caption("Only for: " + "; ".join(f"{k}: {v}" for k, v in filters.items()))
        text = st.text_area(
            "Edit",
            path.read_text(encoding="utf-8"),
            height=200,
            key=f"edit-{note.path}",
            label_visibility="collapsed",
            help="The block between the --- lines at the top (if any) narrows who the note is for.",
        )
        left, right = st.columns(2)
        if left.button("Save changes", key=f"save-{note.path}", type="primary"):
            try:
                split_front_matter(text)
            except Exception as exc:  # show the problem instead of saving a broken note
                st.error(f"The settings block at the top can't be read: {exc}")
            else:
                save_note(root, path, text)
                st.success("Saved. The previous version is kept in memory/_history/.")
                st.rerun()
        if right.button("Archive this note", key=f"archive-{note.path}", icon=":material/archive:"):
            archive_note(root, path)
            st.success("Archived to memory/_archive/. It is no longer used.")
            st.rerun()


def preview(root: Path, settings, configs):
    st.write("See exactly which team notes an agent would receive, and its full instructions.")
    agents, _ = load_agents(root)
    agent = st.selectbox("Agent", list(agents), format_func=lambda a: agents[a].title)
    city = st.selectbox("City", [c.name for c in configs.values()] or ["(none)"])
    parastatal = st.text_input("Parastatal ID (optional)", placeholder="e.g. BWSSB")
    section = st.selectbox("Section (optional)", ["(any)", *section_codes(root)])
    scope = MemoryScope(
        agent=agent,
        step=agents[agent].step,
        city=city,
        parastatals=[parastatal.strip().upper()] if parastatal.strip() else [],
        sections=[] if section == "(any)" else [section],
    )
    chosen, skipped = select_notes(root, scope, settings.vertical, settings.memory_max_chars)
    st.markdown(f"**Team notes used ({len(chosen)})**")
    for note in chosen:
        st.markdown(f"- memory/{note.path}")
    if not chosen:
        st.caption("None.")
    for note in skipped:
        st.warning(
            f"memory/{note.path} matches but is left out: the notes are over the size "
            "limit. Shorten or narrow some notes."
        )
    extra = [f"sections/{section.lower()}"] if section != "(any)" else []
    with st.expander("Full instructions the agent receives"):
        st.code(system_prompt(root, agents[agent], extra), language="markdown", wrap_lines=True)
    if chosen:
        with st.expander("Team context added to its message"):
            st.code(memory_block(chosen), language="markdown", wrap_lines=True)


def agents_view(root: Path):
    st.caption(
        "Read-only here: prompts and skills contain the evidence and URL rules, so "
        "changes go through your developer (edit the files in agent_setup/)."
    )
    agents, _ = load_agents(root)
    st.table(
        pd.DataFrame(
            [
                {
                    "Agent": a.title,
                    "Step": a.step or "checks",
                    "Prompt": a.prompt,
                    "Skills": ", ".join(a.skills),
                    "Tools": ", ".join(a.tools) or "none",
                    "Tool calls (max)": a.max_tool_calls
                    if any(t not in ("web_search", "web_fetch") for t in a.tools)
                    else "",
                    "Model": a.model or "default",
                    "Effort": a.effort,
                }
                for a in agents.values()
            ]
        ).set_index("Agent")
    )
    for a in agents.values():
        with st.expander(a.title, icon=":material/smart_toy:"):
            st.markdown(a.description)
            st.caption(f"agent_setup/agents/{a.path.name}")
    st.subheader("Tools")
    st.caption(
        "web_search and web_fetch run on Anthropic's side; the others are our own "
        "functions, run in the agent's tool loop. Each tool's text below is exactly "
        "what the model is told about it."
    )
    for path in sorted((root / "tools").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        users = [a.title for a in agents.values() if path.stem in a.tools]
        kind = "Anthropic (server)" if meta.get("kind") == "server" else "Ours (client)"
        with st.expander(f"{path.stem}  ·  {kind}  ·  used by: {', '.join(users) or 'nobody'}"):
            st.markdown(body)
    st.subheader("Prompts")
    for path in sorted((root / "prompts").glob("*.md")):
        with st.expander(path.stem):
            st.code(path.read_text(encoding="utf-8"), language="markdown", wrap_lines=True)
    st.subheader("Skills")
    for path in sorted((root / "skills").rglob("*.md")):
        with st.expander(path.relative_to(root / "skills").with_suffix("").as_posix()):
            st.markdown(split_front_matter(path.read_text(encoding="utf-8"))[1])
