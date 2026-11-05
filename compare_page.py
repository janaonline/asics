"""The Scores page for a category scored in the team's templates (read-only).

City first (the sidebar), then the category. Three tabs, all driven by the category's templates:
  Consolidated  People | AI | Difference, like Parastatal_Consolidated_Scoring.xlsx: each section
                out of 10 per city and the total; per parastatal; per question with its roll-up
  Compare       question by question and parastatal by parastatal: both scores, the difference,
                a status, and the evidence side by side
  Files         what was read, and downloads of the AI's workbooks and the compare workbook
Nothing here changes a file.
"""

import dataclasses
from pathlib import Path

import pandas as pd
import streamlit as st

from asics_agent.hosting import can_open
from asics_agent.scoring import compare, compare_run
from asics_agent.scoring.name_resolution import NOT_IN_REGISTER, norm_name, split_label

PRACTICE_NOTE = "Practice results: made-up cities and scripted AI answers."


def _practice_settings(settings):
    """Settings that point at the practice run's files (outputs, register, scoring folder)."""
    outputs = settings.outputs_dir / "practice"
    return dataclasses.replace(
        settings,
        outputs_dir=outputs,
        city_register=outputs / "practice_register.xlsx",
        scoring_dir=settings.scoring_dir / "practice",
    )


@st.cache_data(show_spinner="Reading the scoring files…")
def _view(settings_key: str, _settings, city: str, human: tuple, mtimes: tuple):
    return compare_run.load_view(_settings, city, [Path(p) for p in human])


def _mtimes(paths) -> tuple:
    return tuple((str(p), p.stat().st_mtime) for p in paths if p.exists())


def _frame(table) -> pd.DataFrame:
    return pd.DataFrame(table.rows, columns=table.headers).astype(object)


def render(settings, open_file, city_name: str | None) -> None:
    from ui import header

    header(
        "Scores",
        "People's scores and the AI's, side by side. They are filled in the same templates; "
        "this page only shows them.",
        "Results",
    )
    practice_root = settings.scoring_dir / "practice"
    practice = False
    if (practice_root / "ai").exists() and st.toggle(
        "Show practice results (sample cities, scripted AI)", key="scores-practice"
    ):
        settings, practice = _practice_settings(settings), True
    if practice:
        st.caption(PRACTICE_NOTE)
    only_people = sorted(
        {
            u["city"]
            for u in compare_run.unregistered_places(settings)
            if compare_run.find_city(settings, u["city"]) is None
        }
    )
    if only_people:
        picked = st.selectbox(
            "Or a place only in people's files (not in the register)",
            ["–", *only_people],
            key="scores-people-only",
        )
        city_name = city_name if picked == "–" else picked
    if not city_name:
        st.info("Choose a city in the sidebar.")
        return
    if practice and city_name not in only_people:  # the practice register has its own cities
        from asics_agent.cities import load_register

        register, _ = load_register(settings.city_register)
        names = [c.name for c in register.values()]
        if not names:
            st.info("No practice cities yet. Run a practice Step 1 and Step 2 first.")
            return
        city_name = st.selectbox("Practice city", names)
    st.markdown(f"**{city_name}** · {settings.category_title}")

    humans = compare_run.human_files(settings)
    ais = compare_run.ai_files(settings)
    if not ais and not humans:
        st.info(
            "Nothing to show yet. Run Step 3 (AI scoring) for this city, and upload people's "
            "filled templates in Step 3 > People's scoring, then Merge and calculate."
        )
        return
    view = _view(
        str(settings.scoring_dir) + str(settings.category),
        settings,
        city_name,
        tuple(str(p) for p in humans),
        _mtimes([*humans, *ais]),
    )
    if view.not_in_register:
        st.warning(f"{NOT_IN_REGISTER}.", icon=":material/warning:")
    for note in dict.fromkeys(view.notes):
        st.info(note, icon=":material/info:")
    tabs = st.tabs(["Consolidated", "Compare", "Files"])
    with tabs[0]:
        _consolidated(view, city_name)
    with tabs[1]:
        _compare(view)
    with tabs[2]:
        _files(settings, view, open_file)


# -- Consolidated ---------------------------------------------------------------------------
def _consolidated(view, city_name: str) -> None:
    if not view.tables:
        st.info("No scores to show yet.")
        return
    left, right, last = st.columns([2, 2, 3], vertical_alignment="bottom")
    source = left.radio("Show", ["People", "AI", "Difference"], horizontal=True, key="cons-source")
    name = right.selectbox("View", ["City systems", "Parastatals", "Questions"], key="cons-view")
    only_city = last.toggle(f"Only {city_name}", value=True, key="cons-city")
    table = view.tables.get(source, {}).get(name)
    if not table:
        st.caption("Nothing to show for this view yet.")
        return
    frame = _frame(table)
    if only_city:
        if name in ("City systems", "Parastatals"):
            frame = frame[frame["City"].astype(str).str.casefold() == city_name.casefold()]
        else:
            keep = [
                c
                for c in frame.columns[4:]
                if norm_name(split_label(str(c))[0]) == norm_name(city_name)
            ]
            frame = frame[[*frame.columns[:4], *keep]]
    explain = {
        "City systems": "Each section out of 10 per city (scored main questions over what they "
        "could earn). The total is the average and shows only when every section has a score.",
        "Parastatals": "Per parastatal: the scored main questions and the most they could earn, "
        "per section, and the overall score out of 10.",
        "Questions": "Per question and parastatal. A main question is the sum of its "
        "sub-questions; NA = does not apply; blank = not scored yet.",
    }[name]
    st.caption(
        explain
        + (" Difference is AI minus People." if source == "Difference" else "")
        + " A main question counts only when all its applicable sub-questions are scored."
    )
    st.dataframe(frame, hide_index=True, width="stretch", height=460)


# -- Compare --------------------------------------------------------------------------------
def _compare(view) -> None:
    comp = view.comparison
    if comp is None or not comp.rows:
        st.info("Nothing to compare yet: it needs the AI's file and at least one people's file.")
        return
    rows = comp.rows
    counts = {s: sum(r.status == s for r in rows) for s in compare.STATUSES}
    shown = [(s, n) for s, n in counts.items() if n]
    cols = st.columns(min(len(shown), 6) or 1)
    for col, (status, n) in zip(cols, shown[:6], strict=False):
        col.metric(status[:1].upper() + status[1:], n)
    both = [r for r in rows if r.status == "both"]
    if len(both) >= compare.MIN_ROWS:
        agree = sum(r.agrees == "Yes" for r in both)
        st.caption(f"The AI and people agree exactly on {agree} of {len(both)} compared rows.")
    else:
        st.caption(
            f"Only {len(both)} row(s) are scored by both; a percentage shows from "
            f"{compare.MIN_ROWS}."
        )
    a, b, c, d = st.columns(4)
    sections = sorted({r.section for r in rows})
    section = a.selectbox("Section", ["All", *sections], key="cmp-section")
    status = b.selectbox("Status", ["All", *[s for s, _ in shown]], key="cmp-status")
    units = sorted({r.unit for r in rows})
    unit = c.selectbox("Parastatal", ["All", *units], key="cmp-unit")
    only = d.toggle("Only where they differ", key="cmp-differ")
    view_rows = [
        r
        for r in rows
        if (section == "All" or r.section == section)
        and (status == "All" or r.status == status)
        and (unit == "All" or r.unit == unit)
        and (not only or r.agrees == "No")
    ]
    frame = pd.DataFrame(
        [
            {
                "Parastatal": r.unit,
                "Register": NOT_IN_REGISTER if NOT_IN_REGISTER in r.notes else "",
                "Question": r.code,
                "Status": r.status,
                "People": r.human_score,
                "AI": r.ai_score,
                "Difference": r.difference,
                "Agrees?": r.agrees,
                "Same source?": r.same_source,
                "AI class": r.ai_class,
                "AI confidence": r.ai_confidence,
            }
            for r in view_rows
        ]
    ).astype(object)
    st.caption(
        f"{len(view_rows)} of {len(rows)} rows · click a row to see the evidence side by side"
    )
    event = st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=360,
        on_select="rerun",
        selection_mode="single-row",
        key="cmp-table",
    )
    picked = event.selection.rows if event else []
    if picked:
        _evidence(view_rows[picked[0]])


def _evidence(r) -> None:
    with st.container(border=True):
        st.markdown(f"**{r.unit} · {r.code}** · {r.status}\n\n{r.question}")
        people, ai = st.columns(2)
        with people:
            st.markdown("**People**")
            st.write(f"Score: {r.human_score if r.human_score is not None else '–'}")
            if r.human_source:
                st.markdown(f"Source: {r.human_source}")
            if r.human_location:
                st.caption(r.human_location)
            if r.human_inputs:
                st.caption(f"Inputs: {r.human_inputs}")
            if r.human_comments:
                st.write(r.human_comments)
            if r.scorer:
                st.caption(f"Scored by {r.scorer} ({r.human_file})")
        with ai:
            st.markdown("**AI**")
            st.write(f"Score: {r.ai_score if r.ai_score is not None else '–'} {r.ai_score_from}")
            if r.ai_citation_id:
                st.write(f"Citation: {r.ai_citation_id}")
            link = r.ai_step3_link or r.ai_citation_url
            if link:
                st.markdown(f"Source: {link}")
            if r.ai_where_to_find:
                st.caption(r.ai_where_to_find)
            if r.ai_inputs:
                st.caption(f"Inputs: {r.ai_inputs}")
            if r.ai_quote:
                st.markdown(f"> {r.ai_quote}")
            if r.ai_class or r.ai_confidence:
                st.caption(
                    f"Step 2 class {r.ai_class or '–'} · confidence {r.ai_confidence or '–'}"
                )
        if r.same_source:
            st.caption(f"Same source: {r.same_source}")
        for note in r.notes:
            st.caption(note)


# -- Files ----------------------------------------------------------------------------------
def _files(settings, view, open_file) -> None:
    st.markdown("**The AI's workbooks** (copies of the team's templates)")
    for path in view.ai_paths:
        row = st.container(horizontal=True, vertical_alignment="center")
        row.write(path.name)
        row.download_button(
            "Download",
            path.read_bytes(),
            file_name=path.name,
            key=f"dl-{path.name}",
            icon=":material/download:",
        )
        if can_open(open_file) and row.button(
            "Open", key=f"open-{path.name}", icon=":material/table_view:"
        ):
            open_file(path)
    if not view.ai_paths:
        st.caption("None yet: run Step 3.")
    st.markdown("**People's workbooks** (merged from the uploaded files)")
    for path in view.human_paths:
        row = st.container(horizontal=True, vertical_alignment="center")
        row.write(path.name)
        row.download_button(
            "Download",
            path.read_bytes(),
            file_name=path.name,
            key=f"dl-{path.name}",
            icon=":material/download:",
        )
        if can_open(open_file) and row.button(
            "Open", key=f"open-{path.name}", icon=":material/table_view:"
        ):
            open_file(path)
    if not view.human_paths:
        st.caption("None yet: upload filled templates in Step 3 > People's scoring and merge.")
    st.markdown("**The compare workbook**")
    workbook = compare_run.comparison_workbook(settings, view)
    if workbook is not None and workbook.exists():
        row = st.container(horizontal=True, vertical_alignment="center")
        row.write(workbook.name)
        row.download_button(
            "Download",
            workbook.read_bytes(),
            file_name=workbook.name,
            key="dl-compare",
            icon=":material/download:",
        )
        if can_open(open_file) and row.button(
            "Open", key="open-compare", icon=":material/table_view:"
        ):
            open_file(workbook)
    else:
        st.caption("It needs the AI's file and at least one people's file.")
    with st.expander("What was read and what was ignored"):
        for line in view.reports or ["Nothing read yet."]:
            st.caption(line)
