"""The app's Step 3 · Score page and the Scores page (view only).

Step 3 comes after Step 2: a city can be scored once Step 2 has answered it with the current
Citation Sheet. The AI scores from Step 2's answers and citations only; people score in Excel
(their copies list the same Step 2 evidence). The Scores page shows both side by side."""

import dataclasses
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from asics_agent.scoring import human, workflow
from asics_agent.scoring.ai import scored_cities
from asics_agent.scoring.phase2 import phase2_status
from asics_agent.scoring.recalc import soffice

OPEN = {"file": None}  # the app's "open in Excel" function, set by the page


def _file_card(report, path: Path, open_file, key: str) -> None:
    with st.container(border=True):
        text, buttons = st.columns([3, 2], vertical_alignment="center")
        text.markdown(f"**{path.name}**  \n{report.about.get(path, '')}")
        if not path.exists():
            buttons.caption("Not there any more.")
            return
        row = buttons.container(horizontal=True)
        if (
            open_file
            and path.suffix == ".xlsx"
            and row.button(
                "Open",
                key=f"{key}-open",
                icon=":material/table_view:",
                help="Opens it in Excel on this computer",
            )
        ):
            open_file(path)
        row.download_button(
            "Download",
            path.read_bytes(),
            file_name=path.name,
            key=f"{key}-dl",
            icon=":material/download:",
        )
        if path.name.endswith("_ai.xlsx"):
            _scores_preview(path, key)


def _scores_preview(path: Path, key: str) -> None:
    summary = _ai_summary(str(path), path.stat().st_mtime)
    with st.expander("See the scores here", expanded=False):
        if summary.empty:
            st.caption("Nothing scored yet.")
            return
        st.caption(
            "The same as the workbook's first sheet. **Step 2 answer** is what Step 2 found in "
            "the Citation Sheet; the AI checked it against the source and the workbook turned "
            "its inputs into the **AI score**. 0 means the source shows the provision or "
            "practice is absent; blank means it's left for a person (see Status). Enter your "
            "own scores in the yellow columns in Excel."
        )
        show = st.segmented_control(
            "Show",
            ["All", "Scored by AI", "Left for a person"],
            default="All",
            key=f"{key}-show",
        )
        view = summary if show in (None, "All") else summary[summary["Status"] == show]
        st.dataframe(
            view,
            hide_index=True,
            width="stretch",
            height=380,
            column_config={"Link": st.column_config.LinkColumn("Link", display_text="Open")},
        )


def show_report(report: workflow.StepReport, open_file=None, key: str = "report") -> None:
    """What happened, why rows need a person, the files (open or download), what next."""
    open_file = open_file or OPEN["file"]
    for line in report.done:
        st.success(line, icon=":material/check_circle:")
    if report.breakdown:
        st.markdown("**Why rows were left for a person**")
        st.dataframe(
            pd.DataFrame(report.breakdown, columns=["Reason", "Rows"]),
            hide_index=True,
            width="stretch",
        )
    if report.files:
        main = [f for f in report.files if f not in report.other]
        for i, path in enumerate(main):
            _file_card(report, path, open_file, f"{key}-{i}")
        rest = [f for f in report.files if f in report.other]
        if rest:
            with st.expander(f"Other files ({len(rest)})"):
                for i, path in enumerate(rest):
                    _file_card(report, path, open_file, f"{key}-o{i}")
    if report.next_steps:
        st.markdown("**What next**")
        st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(report.next_steps, 1)))
    if report.problems:
        with st.container(border=True):
            st.markdown(f"**Needs a look ({len(report.problems)})**")
            for line in report.problems:
                st.markdown(f"- {line}")


@st.cache_data(show_spinner=False)
def _ai_summary(path: str, mtime: float) -> pd.DataFrame:
    """The review sheet of the AI's workbook (calculated scores included)."""
    from asics_agent.scoring.ai import OLD_REVIEW_SHEETS, REVIEW_SHEET

    sheets = pd.ExcelFile(path).sheet_names
    name = next((n for n in (REVIEW_SHEET, *OLD_REVIEW_SHEETS) if n in sheets), None)
    if name is None:  # an AI workbook from before this sheet existed
        return pd.DataFrame()
    frame = pd.read_excel(path, sheet_name=name, keep_default_na=False, na_values=[""])
    frame = frame.fillna("")
    columns = [
        "Question",
        "Row",
        "Question text",
        "AI score",
        "Max score",
        "★ Your score",
        "Agrees with AI?",
        "Status",
        "Step 2 status",
        "Step 2 answer",
        "Citation",
        "Link",
        "AI's reasoning",
        "Why left for a person",
    ]
    return _shown(frame[[c for c in columns if c in frame.columns]])


def _shown(frame: pd.DataFrame) -> pd.DataFrame:
    """Score columns mix numbers with "?" / "NA": show them as text."""
    mixed = [c for c in frame.columns if frame[c].dtype == object]
    return frame.astype({c: str for c in mixed}).replace({"nan": "", "None": ""})


@st.cache_data(show_spinner=False)
def _sheet(path: str, sheet: str, mtime: float) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, keep_default_na=False, na_values=[""])


# -- the AI run, in the background (survives leaving the page) ----------------------------


@st.cache_resource
def _jobs() -> dict:
    return {"current": None}


def _start_ai(settings, vertical, codes, cities, practice) -> None:
    job = {
        "started": datetime.now(),
        "done": 0,
        "total": 0,
        "report": None,
        "error": None,
        "cities": cities,
        "practice": practice,
    }

    def progress(i, n):
        job["done"], job["total"] = i, n

    def work():
        try:
            job["report"] = workflow.ai_score(
                settings,
                vertical,
                codes=codes,
                cities=cities,
                practice=practice,
                on_progress=progress,
            )
        except Exception as exc:  # shown on the page; details in the terminal
            job["error"] = f"{type(exc).__name__}: {exc}"

    _jobs()["current"] = job
    threading.Thread(target=work, daemon=True, name="step3-ai").start()


def ai_running() -> bool:
    job = _jobs()["current"]
    return bool(job and job["report"] is None and job["error"] is None)


@st.fragment(run_every=2)
def _ai_progress() -> None:
    job = _jobs()["current"]
    if job is None:
        return
    who = ", ".join(job["cities"]) + (" (practice)" if job["practice"] else "")
    if (job["report"] or job["error"]) and not job.get("shown"):
        job["shown"] = True  # finished: refresh the whole page once (buttons, city table)
        st.rerun(scope="app")
    if job["report"] is None and job["error"] is None:
        total = job["total"]
        text = (
            f"Scoring {who}: {job['done']} of {total} rows"
            if total
            else f"Scoring {who}: preparing…"
        )
        st.progress(job["done"] / total if total else 0.0, text=text)
        st.caption("You can leave this page; scoring carries on.")


def _ai_result() -> None:
    """The last finished AI scoring: outside the live part, so its buttons stay put."""
    job = _jobs()["current"]
    if job is None or (job["report"] is None and job["error"] is None):
        return
    who = ", ".join(job["cities"]) + (" (practice)" if job["practice"] else "")
    st.markdown(f"#### Last AI scoring · {who} · {job['started']:%d %b %H:%M}")
    if job["error"]:
        st.error(f"Step 3 stopped: {job['error']}", icon=":material/error:")
    else:
        show_report(job["report"], key="ai")


# -- Step 3 · Score ------------------------------------------------------------------------


def _readiness(settings, register, practice: bool) -> pd.DataFrame:
    outputs = settings.outputs_dir / "practice" if practice else settings.outputs_dir
    scoring = settings.scoring_dir / "practice" if practice else settings.scoring_dir
    scored = scored_cities(scoring, workflow.step3_vertical(settings))
    rows = []
    for city in register.values():
        status = phase2_status(dataclasses.replace(settings, outputs_dir=outputs), city.name)
        last = scored.get(city.name, "")
        stale = bool(last and status.answered_at and status.answered_at.isoformat() > last)
        rows.append(
            {
                "City": city.name,
                "Ready for Step 3?": "✅ Ready" if status.ready else "⏳ Not yet",
                "Step 2": status.reason,
                "AI scored": (
                    datetime.fromisoformat(last).strftime("%d %b %Y %H:%M")
                    + (" (before the latest answers)" if stale else "")
                )
                if last
                else "–",
            }
        )
    return pd.DataFrame(rows)


def _ai_section(settings, register_fn) -> None:
    vertical = workflow.step3_vertical(settings)
    st.markdown(f"#### AI scoring · {settings.vertical_title}")
    st.caption(
        "The AI scores each question from its Step 2 answer and the reviewed Citation Sheet, "
        "with no web research. It must name the Citation ID and quote it word for word; both "
        "are checked. Where Step 2 found no evidence, the row is left for a person."
    )
    practice = st.toggle(
        "Practice with sample data (free; uses the practice cities from Steps 1 and 2)",
        key="step3-practice",
    )
    if practice:
        from asics_agent.cities import load_register

        register, _ = (
            load_register(settings.outputs_dir / "practice" / "practice_register.xlsx")
            if (settings.outputs_dir / "practice" / "practice_register.xlsx").exists()
            else ({}, [])
        )
    else:
        register, _ = register_fn()
    if not register:
        st.info(
            "No cities yet."
            + (
                " Run a practice Step 1 and Step 2 first."
                if practice
                else " Add them in the City register."
            )
        )
        return
    table = _readiness(settings, register, practice)
    st.dataframe(table, hide_index=True, width="stretch")
    ready = table.loc[table["Ready for Step 3?"].str.startswith("✅"), "City"].tolist()
    if not ready:
        st.warning(
            "No city is ready yet. Step 3 comes after Step 2: answer a city's questions first.",
            icon=":material/hourglass_top:",
        )
        return
    preselect = [c for c in st.session_state.pop("preselect-step3", []) if c in ready]
    if preselect:
        st.session_state["step3-cities"] = preselect
    cities = st.multiselect(
        "Cities to score", ready, key="step3-cities", placeholder="Choose cities that are ready"
    )
    template = None
    if not practice:
        _, templates, _ = workflow._plan(settings)
        template = templates.get(vertical)
        if template is None:
            st.error(
                f"There's no {vertical} scoring workbook on the Verticals sheet of the "
                "assignments workbook (see People's scoring below)."
            )
            return
    codes = st.multiselect(
        "Questions (leave empty for all)",
        list(template.questions) if template else [],
        key="step3-codes",
        disabled=practice,
        placeholder="All questions",
    )
    if soffice() is None:
        st.warning(
            "LibreOffice isn't installed, so the AI's scores can't be calculated yet. "
            "Install it (free) from libreoffice.org.",
            icon=":material/warning:",
        )
    if ai_running():
        st.button("Scoring is running…", disabled=True, icon=":material/hourglass_top:")
    elif st.button(
        "Start Step 3 (AI scoring)",
        type="primary",
        icon=":material/play_arrow:",
        disabled=not cities,
    ):
        _start_ai(settings, vertical, codes or None, cities, practice)
        st.rerun()
    _ai_progress()
    _ai_result()


def _people_section(settings, open_file) -> None:
    st.markdown("#### People's scoring")
    st.caption(
        "Interns score in Excel; their scores are the golden dataset for checking the AI. For "
        f"{settings.vertical_title}, each copy includes only cities Step 2 "
        "has answered, and a **Step 2 evidence** sheet with the citation for every row."
    )
    st.markdown(
        "1. **Assign questions** in the assignments workbook: who scores which questions for "
        "which cities. One question can be split between interns by city.\n"
        "2. **Make interns' copies.** Existing copies are never replaced.\n"
        "3. Interns fill in their copies in Excel.\n"
        "4. **Merge and calculate** puts everyone's work together and updates the scores. Run "
        "it as often as you like."
    )
    row = st.container(horizontal=True)
    if row.button("Open the assignments workbook", icon=":material/assignment_ind:"):
        open_file(workflow.assignments_path(settings))
    if row.button("Check workbooks", icon=":material/rule:"):
        with st.spinner("Checking…"):
            st.session_state["scoring-report"] = workflow.check(settings)
    if row.button("Make interns' copies", icon=":material/content_copy:"):
        with st.spinner("Making copies…"):
            st.session_state["scoring-report"] = workflow.prepare(settings)
    if row.button("Merge and calculate", icon=":material/calculate:"):
        with st.spinner("Merging and calculating (about a minute per vertical)…"):
            st.session_state["scoring-report"] = workflow.merge(settings)
    if report := st.session_state.get("scoring-report"):
        st.markdown(f"##### {report.title}")
        show_report(report, key="people")
    _interns(settings, open_file)


def _interns(settings, open_file) -> None:
    plan, _, _ = workflow._plan(settings)
    if not plan.assignments:
        return
    rows = []
    for a in plan.assignments:
        path = human.intern_file(settings.scoring_dir, a.vertical, a.intern)
        rows.append(
            {
                "Vertical": a.vertical,
                "Intern": a.intern,
                "Questions": ", ".join(a.questions),
                "Rows": len(a.rows),
                "Copy made?": "Yes" if path.exists() else "Not yet",
            }
        )
    with st.expander(f"Interns ({len(rows)} assignments)", icon=":material/group:"):
        picked = st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="scoring-interns",
        )
        if picked.selection.rows:
            a = plan.assignments[picked.selection.rows[0]]
            path = human.intern_file(settings.scoring_dir, a.vertical, a.intern)
            if path.exists() and st.button(f"Open {path.name}", icon=":material/table_view:"):
                open_file(path)
        for path in sorted((settings.scoring_dir / "merged").glob("*_human.xlsx")):
            st.markdown(f"**Latest merge · {path.stem.replace('_human', '')}**")
            st.dataframe(
                _sheet(str(path), "Merge report", path.stat().st_mtime),
                hide_index=True,
                width="stretch",
            )
            if st.button("Open merged workbook", key=f"open-{path}", icon=":material/table_view:"):
                open_file(path)


def render_step3(settings, open_file, register_fn) -> None:
    from ui import header

    OPEN["file"] = open_file

    header(
        "Score",
        "After Step 2: score each question from its answer and citation. The AI "
        "and people fill in the same scoring workbook; compare them on the Scores page.",
        "Step 3",
    )
    tabs = st.tabs(["AI scoring", "People's scoring"])
    with tabs[0]:
        _ai_section(settings, register_fn)
    with tabs[1]:
        _people_section(settings, open_file)


# -- Scores (view only) --------------------------------------------------------------------


def render_scores(settings, open_file) -> None:
    from ui import header

    header(
        "Scores",
        "City scores from people and from the AI, side by side. Edit scores in "
        "Excel; this page only shows them.",
        "Results",
    )
    path = settings.scoring_dir / "results" / workflow.RESULTS_FILE
    practice = settings.scoring_dir / "practice" / "results" / workflow.RESULTS_FILE
    if practice.exists() and st.toggle(
        "Show practice results (sample AI scores)", key="scores-practice"
    ):
        path = practice
    if not path.exists():
        st.info("No scores yet. Run Step 3 (after Step 2) to see them here.")
        return
    cities = _sheet(str(path), "City scores", path.stat().st_mtime)
    cities = cities[cities["City"].notna() & ~cities["City"].astype(str).str.startswith("ASICS")]
    scored = [
        c for c in cities.columns if "(" in c and not c.startswith(("ASICS", "Main questions"))
    ]
    for source in ("People", "AI"):
        cols = [c for c in scored if c.endswith(f"({source})")]
        if cols:
            numbers = cities[cols].apply(pd.to_numeric, errors="coerce")
            cities[f"ASICS score ({source})"] = numbers.mean(axis=1).round(2)
    st.markdown(
        "**City scores**: each vertical out of 10; the ASICS score is their average. "
        "Scores are provisional while main questions are not yet scored."
    )
    st.dataframe(_shown(cities), hide_index=True, width="stretch")

    questions = _sheet(str(path), "Question scores", path.stat().st_mtime)
    st.markdown("**Question scores**")
    left, mid, right = st.columns(3)
    vertical = left.selectbox("Vertical", ["All", *questions["Vertical"].dropna().unique()])
    city = mid.selectbox("City", ["All", *questions["City"].dropna().unique()])
    only = right.toggle("Only where people and AI differ", value=False)
    view = questions
    if vertical != "All":
        view = view[view["Vertical"] == vertical]
    if city != "All":
        view = view[view["City"] == city]
    if only:
        view = view[view["Same score?"] == "No"]
    st.dataframe(_shown(view), hide_index=True, width="stretch", height=420)
    row = st.container(horizontal=True)
    if row.button("Open the results workbook", icon=":material/table_view:"):
        open_file(path)
    row.download_button(
        "Download it", path.read_bytes(), file_name=path.name, icon=":material/download:"
    )
    ai = settings.scoring_dir / ("practice/ai" if path == practice else "ai")
    for copy in sorted(ai.glob("*_ai.xlsx")):
        if row.button(
            f"Open the AI's workbook ({copy.stem.replace('_ai', '')})",
            icon=":material/smart_toy:",
            key=f"open-{copy}",
        ):
            open_file(copy)


def city_scored_at(settings, city: str) -> str | None:
    """When the AI last scored this city (ISO time), for the Home page."""
    return scored_cities(settings.scoring_dir, workflow.step3_vertical(settings)).get(city)
