"""ASICS Parastatal Assessment: the app for the research team.

Start it by double-clicking "Start ASICS.command" (Mac) or "Start ASICS.bat" (Windows),
or run:  uv run streamlit run app.py
"""

import io
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from asics_agent.applicability import applies_to
from asics_agent.cities import load_register
from asics_agent.config import get_settings
from asics_agent.links.accessibility import make_http_client
from asics_agent.practice import PRACTICE_NOTE, fake_http, practice_services
from asics_agent.question_bank import load_question_bank
from asics_agent.recheck import recheck_workbook, summary_text
from asics_agent.reporting import (
    STATUS_HELP,
    VERIFICATION_HELP,
    answer_summary,
    headline,
    severity_label,
    team_issues,
)
from asics_agent.run_options import RunOptions
from asics_agent.runner import BatchRun, PipelineRun
from asics_agent.services import default_services
from asics_agent.sources_workbook import read_sources_workbook, sources_path, workspace_for
from asics_agent.workbook import city_outcome, coverage_counts
from ui import header, setup_page_chrome, sidebar_footer, step_card

st.set_page_config(
    page_title="ASICS · Janaagraha", page_icon=":material/fact_check:", layout="wide"
)
setup_page_chrome()
settings = get_settings()

MODES = {
    "real": "Real run: researches the web with Claude (uses the internet, costs money)",
    "practice": "Practice run: sample data, free. Good for learning the app",
    "checks": "Checks only: free. Checks the question bank and shows which questions apply",
}
OUTCOME_ICON = {"Done": ":material/check_circle:", "Stopped": ":material/pause_circle:"}


@st.cache_resource
def run_store() -> dict:
    """Runs live here so they keep going if the page is refreshed."""
    return {"current": None}


@st.cache_data
def question_bank():
    questions, _ = load_question_bank(settings.question_bank)
    return questions


def register(path: Path | None = None):
    """Read the city register fresh each time, so the team's edits show up straight away."""
    return load_register(path or settings.city_register)


def zip_folder(folder: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(folder.parent))
    return buffer.getvalue()


def show_issue(issue) -> None:
    box = {"error": st.error, "warning": st.warning, "info": st.info}[issue.severity]
    about = f" · {issue.ref}" if issue.ref and not issue.message.startswith(issue.ref) else ""
    box(f"**{severity_label(issue.severity)}**{about}: {issue.message}")


def open_file(path: Path) -> None:
    """Open a file in its usual program (e.g. Excel) on this computer."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 (Windows only)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def count_questions(city, parastatal_ids, pillars, wanted) -> int:
    return sum(
        1
        for p in city.parastatals
        if p.id in parastatal_ids
        for q in question_bank().values()
        if q.pillar in pillars
        and not q.is_rollup
        and applies_to(q, p) is not False
        and (not wanted or q.id in wanted or q.raw_id in wanted or q.parent_id in wanted)
    )


# ---------------------------------------------------------------------------------------
# Start a run
# ---------------------------------------------------------------------------------------


def city_sources(settings_, city) -> tuple[Path, list, list] | None:
    """(path, parastatals, citations) of a city's Sources workbook, if it exists."""
    workspace = workspace_for(settings_.outputs_dir, city.name)
    path = sources_path(workspace, city.name)
    if not path.exists():
        return None
    parastatals, citations, _ = read_sources_workbook(path, workspace / "evidence")
    return path, parastatals, citations


START_HEADERS = {
    "sources": (
        "Find parastatals and sources",
        "Step 1",
        "The agent finds each city's "
        "parastatals, checks their websites and builds the Citation Sheet. You review "
        "the parastatals before any sources are researched.",
    ),
    "answers": (
        "Answer questions",
        "Step 2",
        "Answers every applicable question using only "
        "the reviewed Citation Sheet, citing the row it relies on.",
    ),
    "checks": (
        "Question bank check",
        "Settings",
        "A free check of the question bank and the city register. No web research.",
    ),
}


def step1_page():
    start_page("sources")


def step2_page():
    start_page("answers")


def checks_page():
    start_page("checks")


def start_page(action: str):
    title, kicker, lede = START_HEADERS[action]
    header(title, lede, kicker)
    current = run_store()["current"]
    if current and current.status in {"running", "waiting_for_review"}:
        st.info("A run is already in progress.", icon=":material/hourglass_top:")
        if st.button("Go to the current run", type="primary"):
            st.switch_page(PAGES["run"])
        return

    practice = st.checkbox(
        "Practice with sample data (free, takes seconds)",
        value=False,
        help="Uses two made-up cities and question UPD 1, so you can see "
        "every step, including the review, without cost.",
    )
    # A short pause per step makes practice runs look like real ones (progress, review).
    services = practice_services(settings, delay=1.5) if practice else None
    run_settings = services.settings if services else settings
    configs, register_issues = register(run_settings.city_register)
    questions = question_bank()
    must_fix = [i for i in register_issues if i.severity == "error"]
    if must_fix and not practice:
        st.warning(
            f"The city register has {len(must_fix)} problem(s). See **City register**.",
            icon=":material/warning:",
        )
    if not configs:
        st.error("No cities are ready. Open **City register** to add one.")
        return

    step = "answers" if action == "answers" else "sources"
    chosen_cities = st.multiselect(
        "Cities",
        list(configs),
        # A city chosen on Home is preselected; otherwise the first city.
        default=list(configs)[:2]
        if practice
        else [
            c
            for c in st.session_state.get(
                f"preselect-{'step1' if step == 'sources' else 'step2'}", list(configs)[:1]
            )
            if c in configs
        ],
        format_func=lambda c: configs[c].name,
    )
    chosen: dict[str, list[str] | None] = {}
    blocked_cities = []
    if step == "sources" and action != "checks":
        st.caption(
            "The register's list of parastatals is only a starting point; the agent finds the rest."
        )
    if action == "answers":
        for slug in chosen_cities:
            found = city_sources(run_settings, configs[slug])
            if found is None:
                st.error(
                    f"{configs[slug].name} has no Sources workbook yet. Run Step 1 for it first.",
                    icon=":material/block:",
                )
                blocked_cities.append(slug)
                continue
            path, parastatals, citations = found
            included = [p for p in parastatals if p.include]
            usable = sum(
                c.use_for_answers and c.verification_status == "Verified" for c in citations
            )
            names = {p.id: f"{p.name} ({p.id})" for p in included}
            with st.expander(
                f"{configs[slug].name}: {len(included)} parastatal(s), {usable} "
                f"citation(s) ready to use"
            ):
                st.caption(
                    f"Sources workbook last saved "
                    f"{datetime.fromtimestamp(path.stat().st_mtime):%d %b %Y %H:%M}"
                )
                chosen[slug] = st.multiselect(
                    "Parastatals to answer",
                    list(names),
                    default=list(names),
                    format_func=names.get,
                    key=f"p-{slug}",
                )
    if practice:
        chosen_pillars, only = ["UPD"], "UPD 1"
    else:
        pillars = {q.pillar: q.pillar_name for q in questions.values()}
        chosen_pillars = st.multiselect(
            "Sections of the question bank",
            list(pillars),
            default=list(pillars),
            format_func=pillars.get,
        )
        only = ""
    upload = None
    if not practice and action != "checks":
        with st.expander("More options"):
            only = st.text_input(
                "Only these questions (optional)",
                placeholder="e.g. UPD 1, DPG 5a",
                help="A main question (e.g. UPD 1) includes its sub-questions.",
            )
            if len(chosen_cities) == 1:
                label = (
                    "Previous workbook whose Citation Sheet links to re-check (optional)"
                    if step == "sources"
                    else "Workbook to write the answers into (optional)"
                )
                upload = st.file_uploader(label, type=["xlsx"])
            else:
                st.caption("A previous workbook can only be added when one city is chosen.")

    options = RunOptions()
    if not practice and action != "checks":
        with st.expander("Advanced options (for this run only)"):
            st.caption("Leave these empty to use each agent's own settings (Agent setup).")
            model = st.text_input(
                "Claude model for agents without their own",
                placeholder=f"default: {settings.model}",
            )
            effort = st.selectbox(
                "Effort for every agent", ["(agents' own)", "low", "medium", "high", "xhigh", "max"]
            )
            searches = st.number_input(
                "Web searches per research call (0 = agents' own)",
                min_value=0,
                max_value=30,
                value=0,
            )
            options = RunOptions(
                model=model.strip() or None,
                effort=None if effort.startswith("(") else effort,
                web_search_max_uses=int(searches) or None,
            )
    wanted = {w.strip() for w in only.split(",") if w.strip()} if only else set()
    runnable = [c for c in chosen_cities if c not in blocked_cities]
    if action == "answers":
        total = 0
        for slug in runnable:
            parastatals = [
                p
                for p in city_sources(run_settings, configs[slug])[1]
                if p.id in (chosen.get(slug) or [])
            ]
            city = configs[slug].model_copy(update={"parastatals": parastatals})
            total += count_questions(city, [p.id for p in parastatals], chosen_pillars, wanted)
        st.markdown(
            f"**{total} questions** will be answered in **{len(runnable)} city(ies)**, "
            "using only their Citation Sheets."
        )
    elif action == "sources":
        st.markdown(f"Sources will be researched for **{len(runnable)} city(ies)**.")

    blocked = not runnable or not chosen_pillars
    needs_key = action != "checks" and not practice
    if needs_key and not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        st.error(
            "This needs an Anthropic API key. Ask your developer to add it to the .env "
            "file, then restart the app.",
            icon=":material/key_off:",
        )
        blocked = True
    elif needs_key:
        st.caption(
            "Real runs cost money and take time; cities are done one after another. You "
            "can leave this page and come back while the black window stays open."
        )

    if st.button(
        {"sources": "Start Step 1", "answers": "Start Step 2", "checks": "Run the check"}[action],
        type="primary",
        disabled=blocked,
        icon=":material/play_arrow:",
    ):
        base = None
        if upload is not None:
            uploads = settings.outputs_dir / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            base = uploads / f"{datetime.now():%Y%m%d-%H%M%S}-{upload.name}"
            base.write_bytes(upload.getvalue())
        inputs = {
            "only_pillars": chosen_pillars,
            "only_questions": sorted(wanted) or None,
            "base_workbook": str(base) if base else None,
            "skip_research": action == "checks",
        }
        kind = {"sources": "Step 1: Sources", "answers": "Step 2: Answers", "checks": "Checks"}[
            action
        ]
        where = configs[runnable[0]].name if len(runnable) == 1 else f"{len(runnable)} cities"
        run_store()["current"] = BatchRun(
            services or default_services(),
            {c: configs[c].name for c in runnable},
            inputs,
            {c: chosen.get(c) for c in runnable} if action == "answers" else None,
            label=f"{'Practice · ' if practice else ''}{kind} · {where}",
            step=step,
            options=options,
        ).start()
        st.switch_page(PAGES["run"])


# ---------------------------------------------------------------------------------------
# Current run
# ---------------------------------------------------------------------------------------
def run_page():
    batch: BatchRun | None = run_store()["current"]
    if batch is None:
        header("Current run", "Nothing is running. Start Step 1 or Step 2.", "Assess")
        st.page_link(
            PAGES["step1"],
            label="Go to Step 1: Find parastatals and sources",
            icon=":material/arrow_forward:",
        )
        return
    header(batch.label, f"Started {batch.started:%d %b %Y, %H:%M}", "Current run")

    if batch.status == "running":
        live_progress(batch)
    elif batch.status == "waiting_for_review":
        review_panel(batch)
    elif batch.status == "failed":
        st.error(batch.error, icon=":material/error:")
    else:
        results_panel(batch)


def city_state(batch: BatchRun, slug: str, run: PipelineRun) -> str:
    if slug == batch.current:
        return "Working on it now"
    if run.status == "waiting_for_review":
        return "Parastatals found; waiting for the review"
    if run.status in {"finished", "failed"}:
        return city_outcome(run)
    return "Waiting its turn"


def ago(when: datetime) -> str:
    minutes = int((datetime.now() - when).total_seconds() // 60)
    return "just now" if minutes < 1 else f"{minutes} min ago"


@st.fragment(run_every=2)
def live_progress(batch: BatchRun):
    if batch.status != "running":
        st.rerun()  # redraw the whole page for the next step
    run = batch.runs.get(batch.current) if batch.current else None
    elapsed = int((datetime.now() - batch.started).total_seconds() // 60)
    st.info(
        f"**Working, nothing for you to do right now.** Running for {elapsed} min"
        + (f"; last activity {ago(run.last_event)}." if run else ".")
        + " You can leave this page and come back; keep the black window open.",
        icon=":material/hourglass_top:",
    )
    if len(batch.runs) > 1:
        st.table(
            pd.DataFrame(
                [(r.label, city_state(batch, s, r)) for s, r in batch.runs.items()],
                columns=["City", "Progress"],
            ).set_index("City")
        )
    if run is None:
        return
    st.markdown(f"#### {run.label}")
    if run.links_total:
        st.progress(
            min(run.links_done / run.links_total, 1.0),
            f"Citation Sheet: {run.links_done} of {run.links_total} parastatals finished",
        )
    if run.answers_total:
        st.progress(
            min(run.answers_done / run.answers_total, 1.0),
            f"Questions: {run.answers_done} of {run.answers_total} answered",
        )
    if run.activity:
        st.markdown("**Right now**")
        st.table(
            pd.DataFrame(
                [(key, text, ago(when)) for key, (when, text) in run.activity.items()],
                columns=["Parastatal", "What it is doing", "Updated"],
            ).set_index("Parastatal")
        )
    with st.expander("What has happened so far", expanded=not run.activity):
        for line in run.log[-25:]:
            st.text(line)


BAND_ICON = {
    "Official": ":material/verified:",
    "Probably official": ":material/help:",
    "Not confirmed": ":material/gpp_bad:",
}


def review_panel(batch: BatchRun):
    reviews = batch.reviews
    total = sum(len(r.get("parastatals", [])) for r in reviews.values())
    st.warning(
        f"**Action needed: the run is paused until you review the {total} parastatal(s) "
        "below.** Untick any you don't want researched, then press **Continue** (here or at "
        "the bottom). Unticked ones stay in the Sources workbook as Include? = No, so you can "
        "add them back later.",
        icon=":material/front_hand:",
    )
    top_go = st.button(
        "Continue with the ticked parastatals",
        type="primary",
        icon=":material/play_arrow:",
        key="go-top",
    )
    decisions = {}
    for slug, review in reviews.items():
        messages = {}
        for issue in review.get("issues", []):
            if issue.get("audience") == "team":
                messages.setdefault(issue.get("ref"), []).append(issue["message"])
        with st.container(border=True):
            head, tick = st.columns([3, 2])
            head.markdown(f"### {batch.runs[slug].label}")
            include_city = tick.toggle("Include this city", value=True, key=f"city-{slug}")
            keep = []
            for p in review.get("parastatals", []):
                pid, check = p["id"], p.get("website_check")
                with st.container(border=True):
                    top, box = st.columns([5, 1])
                    who = (
                        "listed by your team"
                        if p["found_by"] == "Your team"
                        else "found by the agent"
                    )
                    top.markdown(f"**{p['name']}** ({pid}), {who}")
                    if box.checkbox(
                        "Include", value=True, key=f"keep-{slug}-{pid}", disabled=not include_city
                    ):
                        keep.append(pid)
                    if p.get("why_included"):
                        st.caption(p["why_included"])
                    website = p.get("official_website") or "not confirmed"
                    st.markdown(
                        f"Website: {website}  \n"
                        f"Law that created it: {p.get('governing_act') or 'not found'}  \n"
                        f"Current status: {p.get('current_status') or 'unknown'}  \n"
                        f"Questions to answer: "
                        f"{sum(not question_bank()[q].is_rollup for q in review['applicability'].get(pid, []))}"
                    )
                    if check:
                        with st.expander(
                            f"Website check: {check['score']}/100, {check['band']}",
                            icon=BAND_ICON.get(check["band"]),
                        ):
                            st.caption(check["url"])
                            for reason in check["reasons"]:
                                st.markdown(f"- {reason}")
                    for message in messages.get(pid, []):
                        st.warning(message, icon=":material/help:")
            decisions[slug] = (
                {"action": "edit", "parastatals": keep}
                if include_city and keep
                else {"action": "stop"}
            )

    going = sum(d["action"] != "stop" for d in decisions.values())
    go, stop = st.columns([2, 3])
    bottom_go = go.button(
        f"Continue with {going} city(ies)",
        type="primary",
        disabled=not going,
        icon=":material/play_arrow:",
        key="go-bottom",
    )
    if (top_go or bottom_go) and going:
        batch.submit_review(decisions)
        st.rerun()
    if stop.button("Stop here (save the list, research nothing)", icon=":material/stop:"):
        batch.submit_review({slug: {"action": "stop"} for slug in reviews})
        st.rerun()


def sources_results(slug: str, run: PipelineRun):
    values = run.result or {}
    parastatals = values.get("parastatals", [])
    sources = values.get("final_sources", [])
    covered, missing = coverage_counts(values) if values.get("questions") else (0, 0)
    workbook = values.get("output_workbook")
    if workbook and "_Sources" in workbook:
        left, right = st.columns(2)
        if left.button(
            "Open the Sources workbook in Excel",
            type="primary",
            icon=":material/edit_document:",
            key=f"open-{slug}",
        ):
            open_file(Path(workbook))
            st.toast("Opening… Review it, save and close it, then run Step 2.")
        right.download_button(
            "Download the Sources workbook",
            Path(workbook).read_bytes(),
            Path(workbook).name,
            icon=":material/download:",
            key=f"dl-{slug}",
        )
        st.markdown(
            f"**{sum(p.include for p in parastatals)}** parastatal(s) included · "
            f"**{sum(s.verification_status == 'Verified' for s in sources)}** citation(s) "
            f"verified · **{covered}** question(s) have a source · **{missing}** have none yet"
        )
    if parastatals:
        st.table(
            pd.DataFrame(
                [
                    {
                        "Parastatal": f"{p.name} ({p.id})",
                        "Found by": p.found_by,
                        "Included": "Yes" if p.include else "No",
                        "Website": p.official_website or "not confirmed",
                        "Website check": f"{p.website_check.score}/100 ({p.website_check.band})"
                        if p.website_check
                        else "",
                    }
                    for p in parastatals
                ]
            ).set_index("Parastatal")
        )


def answers_results(slug: str, run: PipelineRun):
    answers, issues = run.answers, run.issues
    questions = question_bank()
    if answers:
        st.write(headline(answers, issues))
    if run.output_dir and (workbook := next(run.output_dir.glob("ASICS_*.xlsx"), None)):
        st.download_button(
            f"Download the {run.label} answers workbook",
            workbook.read_bytes(),
            workbook.name,
            type="primary",
            icon=":material/download:",
            key=f"wb-{slug}",
        )
    if answers:
        st.table(
            pd.DataFrame(
                answer_summary(answers), columns=["Status", "Questions", "What it means"]
            ).set_index("Status")
        )
        rows = [
            {
                "Parastatal": a.parastatal_id,
                "Question": questions[a.question_id].raw_id,
                "Status": a.status,
                "Citation": a.citation_id,
                "Source": a.citation_url or None,
                "Where to find it": a.where_to_find,
                "Answer": a.answer or a.missing_evidence,
            }
            for a in sorted(answers, key=lambda a: (a.parastatal_id, questions[a.question_id].row))
        ]
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Question": st.column_config.TextColumn(width="small"),
                "Citation": st.column_config.TextColumn(width="small"),
                "Source": st.column_config.LinkColumn("Source", display_text="Open"),
            },
        )


def results_panel(batch: BatchRun):
    runs = batch.runs
    done = sum(city_outcome(r) == "Done" for r in runs.values())
    st.success(f"Finished: {done} of {len(runs)} city(ies) done.", icon=":material/check_circle:")
    if batch.label.startswith("Practice"):
        st.warning(PRACTICE_NOTE, icon=":material/school:")
    if batch.step == "sources" and done:
        st.info(
            "**Next:** open each city's Sources workbook, check the parastatals and the "
            "Citation Sheet, add any sources you know, save and close it. Then run **Step 2: "
            "Answer questions**.",
            icon=":material/arrow_forward:",
        )
    for slug, run in runs.items():
        outcome = city_outcome(run)
        icon = next(
            (v for k, v in OUTCOME_ICON.items() if outcome.startswith(k)), ":material/error:"
        )
        with st.expander(f"{run.label}: {outcome}", icon=icon, expanded=len(runs) == 1):
            if batch.step == "sources":
                sources_results(slug, run)
            else:
                answers_results(slug, run)
            team = team_issues(run.issues)
            st.markdown(f"**Needs attention ({len(team)})**")
            for issue in team:
                show_issue(issue)
    if batch.summary_path and len(runs) > 1:
        st.download_button(
            "Download the index of all cities",
            batch.summary_path.read_bytes(),
            batch.summary_path.name,
            icon=":material/table_view:",
        )
    if st.button("Start another run", icon=":material/add:"):
        st.switch_page(PAGES["home"])


# ---------------------------------------------------------------------------------------
# City register
# ---------------------------------------------------------------------------------------
def register_page():
    header(
        "City register",
        "The cities to assess. The agent finds each city's parastatals itself.",
        "Settings",
    )
    path = settings.city_register
    st.write(
        "The list of cities lives in one Excel file that your team maintains. You only "
        "need each city's name, state and city government: the agent finds the "
        "parastatals itself. Edit it in Excel, save it, then press **Check again**."
    )
    st.caption(f"File: {path}")
    a, b, c = st.columns(3)
    if a.button(
        "Open in Excel", type="primary", icon=":material/edit_document:", disabled=not path.exists()
    ):
        open_file(path)
        st.toast("Opening the register… Save and close it when you're done.")
    b.button("Check again", icon=":material/refresh:")
    if path.exists():
        c.download_button(
            "Download a copy", path.read_bytes(), path.name, icon=":material/download:"
        )

    configs, issues = register()
    team = team_issues(issues)
    if team:
        st.subheader(f"Problems to fix ({len(team)})")
        st.caption(
            "To fix: press **Open in Excel**, change the row mentioned, save and close "
            "the file, then press **Check again**."
        )
        for issue in team:
            show_issue(issue)
    else:
        st.success("No problems found in the register.", icon=":material/check_circle:")

    from asics_agent.cities import TYPE_LABELS

    st.subheader(f"Cities ({len(configs)})")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "City": city.name,
                    "State": city.state,
                    "City government (ULG)": city.ulg or "⚠ missing",
                    "Parastatals listed by your team": len(city.parastatals),
                }
                for city in configs.values()
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    listed = [
        {
            "City": city.name,
            "ID": p.id,
            "Name": p.name,
            "Type": TYPE_LABELS[p.type],
            "Raises revenue": p.revenue_raising,
            "Capital works": p.capex_mandate,
            "Annual budget": p.has_annual_budget,
            "Chief executive": p.has_chief_executive,
        }
        for city in configs.values()
        for p in city.parastatals
    ]
    st.subheader(f"Parastatals listed by your team ({len(listed)})")
    st.caption(
        "Optional. The agent finds each city's parastatals itself; these are always "
        "included. The full list for each city is in its Sources workbook (City files)."
    )
    if listed:
        st.dataframe(pd.DataFrame(listed), hide_index=True, use_container_width=True)


def city_folders() -> list[Path]:
    """Real cities first, then practice ones."""
    roots = [settings.outputs_dir / "cities", settings.outputs_dir / "practice" / "cities"]
    return [p for root in roots if root.exists() for p in sorted(root.iterdir()) if p.is_dir()]


def city_workbooks() -> list[Path]:
    """Every Sources and answers workbook, newest first (practice ones included)."""
    found = [p for p in settings.outputs_dir.glob("**/cities/*/ASICS_*_Sources.xlsx")]
    found += [p for p in settings.outputs_dir.glob("**/cities/*/answers/*/ASICS_Parastatal_*.xlsx")]
    return sorted(
        (p for p in found if "re-checked" not in p.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def describe_recheck(path: Path) -> str:
    practice = " (practice)" if "practice" in path.parts else ""
    city = next((p.name for p in path.parents if p.parent.name == "cities"), "")
    kind = "Sources" if "_Sources" in path.name else "Answers"
    when = datetime.fromtimestamp(path.stat().st_mtime)
    return f"{city}{practice}: {kind}, re-checked {when:%d %b %Y %H:%M}"


def describe_workbook(path: Path) -> str:
    practice = " (practice)" if "practice" in path.parts else ""
    kind = "Sources" if path.stem.endswith("_Sources") else "Answers"
    city = path.parents[2].name if kind == "Answers" else path.parent.name
    when = datetime.fromtimestamp(path.stat().st_mtime)
    return f"{city}{practice}: {kind}, {when:%d %b %Y %H:%M}"


def files_page():
    import city_view_page

    city_view_page.render(city_folders(), open_file, zip_folder, header)


def recheck_page():
    header(
        "Re-check links",
        "Check that every link still opens and every quote is still on its page.",
        "Results",
    )
    st.write(
        "Before a review, check that every link in a city's workbook still opens and that each "
        "answer's quote is still on the page. The results are added as new columns in a copy "
        "of the workbook; your original is not changed."
    )
    workbooks = city_workbooks()
    source = st.radio(
        "Which workbook?", ["From past results", "Upload a workbook"], horizontal=True
    )
    path = None
    if source == "From past results" and workbooks:
        path = st.selectbox("City workbook", workbooks, format_func=describe_workbook)
    elif source == "Upload a workbook":
        upload = st.file_uploader("Workbook", type=["xlsx"])
        if upload:
            path = settings.outputs_dir / "uploads" / upload.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(upload.getvalue())
            st.caption(
                "Tip: re-check from Past results where possible, so the saved copies stay linked."
            )
    if st.button("Re-check now", type="primary", disabled=path is None, icon=":material/link:"):
        with st.spinner("Opening every link… this can take a few minutes."):
            practice = "practice" in path.parts  # practice results stay offline
            client = (
                fake_http()
                if practice
                else make_http_client(settings.user_agent, settings.http_timeout)
            )
            out, summary = recheck_workbook(path, client, settings.user_agent)
        problems = summary.get("links with problems", 0) + summary.get(
            "quotes no longer on the page", 0
        )
        (st.warning if problems else st.success)(summary_text(summary))
        st.session_state["recheck-latest"] = str(out)
        st.download_button(
            "Download the re-checked workbook",
            out.read_bytes(),
            out.name,
            icon=":material/download:",
        )

    import city_view_page

    done = sorted(
        settings.outputs_dir.glob("**/*re-checked*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if done:
        st.markdown("#### Results")
        latest = st.session_state.get("recheck-latest")
        index = next((i for i, p in enumerate(done) if str(p) == latest), 0)
        chosen = st.selectbox(
            "Re-check", done, index=index, format_func=lambda p: f"{describe_recheck(p)}"
        )
        city_view_page.recheck_view(chosen)


def setup_page():
    import agent_setup_page

    agent_setup_page.render(settings, register, open_file, show_issue, question_bank)


def help_page():
    header("Help", "How the tool works and how to review its results.")
    st.header("How it works: two steps")
    st.markdown(
        "1. **Step 1: Find parastatals and sources.** For each city, the agent finds the "
        "parastatals itself, checks each one's official website (with a score you can see "
        "point by point), then builds the **Citation Sheet**: the official sources needed to "
        "answer the questions. You review the parastatals before any sources are researched.\n"
        "2. **You review the Sources workbook** (in **City files**). Untick parastatals or "
        "sources you don't want, and add any sources you know about. Nothing is answered yet.\n"
        "3. **Step 2: Answer questions.** Every answer uses **only** the Citation Sheet rows "
        "marked *Use for Answers? = Yes*, and names the **Citation ID** it relies on. If no "
        "source answers a question, it says so, and suggests what kind of source to add."
    )
    st.header("How the official website is checked")
    st.markdown(
        "Each candidate website gets points for: a government web address (gov.in / nic.in, "
        "+40); being linked from other government websites (+20, or +30 for two or more); "
        "opening properly (+10); saying it is run by the government or hosted by NIC (+10); a "
        "government email address (+10); Right to Information details (+5); a social media "
        "account also linked from a government page (+5); its name in the address or title "
        "(+5). Directories, Wikipedia and social media pages score 0.\n\n"
        "**70 or more: Official. 50 to 69: Probably official** (used, but please confirm). "
        "**Below 50: Not confirmed** (not used as the official website; sources are still "
        "researched). A gov.in / nic.in address with the parastatal's own name is treated as "
        "Probably official even if the automatic check couldn't open it, so you can confirm "
        "it by opening the link."
    )
    st.header("How to review the answers")
    st.markdown(
        "1. Open the answers workbook and start with the **Needs Attention** sheet.\n"
        "2. In the scoring sheet, **Citation ID** names the Citation Sheet row used. Click the "
        "**Citation URL**, then use **Where to Find It** and the **Search Phrase** (Ctrl+F on "
        "Windows, Cmd+F on Mac) to find the quote in **Evidence Excerpt**.\n"
        "3. If the website has changed, click **Open saved copy**.\n"
        "4. Choose **Agree / Disagree / Needs change** in **Reviewer Decision** and add a "
        "comment.\n"
        "5. Before sharing, use **Re-check links**."
    )
    st.header("What each status means")
    st.table(
        pd.DataFrame(
            [(s, m, a) for s, (m, a) in STATUS_HELP.items()],
            columns=["Status", "Meaning", "What to do"],
        ).set_index("Status")
    )
    st.header("How links are checked")
    st.markdown(
        "- **Only links found by a search, or added by your team, are used.** A link the AI "
        "wrote itself, or remembered, is thrown away.\n"
        "- **Each exact link is opened separately**, the way a browser would, without changing "
        "it. It must open and show real, readable content (not an error page, a login page, or "
        "just a summary of a document, as on some India Code pages).\n"
        "- **The page's content is saved**, so you can see exactly what was checked.\n"
        "- **Every quote is matched against the saved page.** If an answer's quote isn't on the "
        "page word for word, the answer is marked *Human Verification Required*."
    )
    st.table(
        pd.DataFrame(
            VERIFICATION_HELP.items(), columns=["Verification Status", "Meaning"]
        ).set_index("Verification Status")
    )


def home_page():
    header(
        "Assess a city's parastatals",
        "Three steps: the agent finds the sources, your team reviews them, then the agent "
        "answers the question bank using only the reviewed sources.",
    )
    current = run_store()["current"]
    if current and current.status == "waiting_for_review":
        st.warning("**A run is waiting for your review.**", icon=":material/front_hand:")
        st.page_link(
            PAGES["run"], label="Review the parastatals now", icon=":material/arrow_forward:"
        )
    elif current and current.status == "running":
        st.info(f"**A run is in progress:** {current.label}", icon=":material/hourglass_top:")
        st.page_link(PAGES["run"], label="See its progress", icon=":material/arrow_forward:")

    steps = [
        (
            1,
            "Find sources",
            "Finds each city's parastatals, checks their websites and builds the Citation Sheet.",
            "step1",
            "Start Step 1",
        ),
        (
            2,
            "Review sources",
            "Check the parastatals and sources, untick anything unsuitable, add what you know.",
            "files",
            "Open City files",
        ),
        (
            3,
            "Answer questions",
            "Answers each question using only the reviewed Citation Sheet, citing its row.",
            "step2",
            "Start Step 2",
        ),
    ]
    for column, (number, title, text, page, label) in zip(st.columns(3), steps, strict=True):
        with column.container(border=True):
            step_card(number, title, text)
            st.page_link(PAGES[page], label=label, icon=":material/arrow_forward:")

    st.markdown("#### Your cities")
    cities_overview()
    st.caption(
        "Want to try it first? Tick *Practice with sample data* on Step 1: it's free "
        "and takes seconds."
    )


STAGES = {  # stage -> (label shown in the table, what to do next)
    "not_started": ("⚪ Not started", "Find sources (Step 1)"),
    "sources": ("🔵 Sources ready", "Review sources, then answer (Step 2)"),
    "changed": ("🟠 Sources changed", "Answer again (Step 2)"),
    "answered": ("🟢 Answered", "Review the answers"),
}


@st.cache_data(show_spinner=False)
def _city_status(
    sources: str | None, sources_mtime: float, evidence: str, last_answers: float | None
) -> dict:
    """A city's stage and counts. Cached until its Sources workbook or answers change."""
    if sources is None:
        return {"stage": "not_started", "parastatals": None, "ready": None}
    parastatals, citations, _ = read_sources_workbook(Path(sources), Path(evidence))
    stage = (
        "sources"
        if last_answers is None
        else "answered"
        if last_answers >= sources_mtime
        else "changed"
    )
    return {
        "stage": stage,
        "parastatals": sum(p.include for p in parastatals),
        "ready": sum(c.use_for_answers and c.verification_status == "Verified" for c in citations),
    }


def city_status(city) -> dict:
    workspace = workspace_for(settings.outputs_dir, city.name)
    sources = sources_path(workspace, city.name)
    answers = sorted(
        (workspace / "answers").glob("*/ASICS_Parastatal_*.xlsx"), key=lambda p: p.stat().st_mtime
    )
    exists = sources.exists()
    status = _city_status(
        str(sources) if exists else None,
        sources.stat().st_mtime if exists else 0.0,
        str(workspace / "evidence"),
        answers[-1].stat().st_mtime if answers else None,
    )
    times = ([sources.stat().st_mtime] if exists else []) + (
        [answers[-1].stat().st_mtime] if answers else []
    )
    return {
        **status,
        "sources_path": sources if exists else None,
        "answers_path": answers[-1] if answers else None,
        "last": datetime.fromtimestamp(max(times)) if times else None,
    }


def cities_overview() -> None:
    """All cities in one compact, filterable table; actions for the selected city below."""
    configs, _ = register()
    if not configs:
        st.caption("No cities yet. Add one in the City register.")
        return
    statuses = {slug: city_status(city) for slug, city in configs.items()}
    counts = {stage: sum(s["stage"] == stage for s in statuses.values()) for stage in STAGES}

    left, right = st.columns([3, 1], vertical_alignment="bottom")
    options = ["all", *[stage for stage in STAGES if counts[stage]]]
    stage = (
        left.pills(
            "Show",
            options,
            default="all",
            key="home-stage",
            format_func=lambda o: (
                f"All {len(configs)}" if o == "all" else f"{STAGES[o][0]} {counts[o]}"
            ),
        )
        or "all"
    )
    search = right.text_input(
        "Search", placeholder="City or state", key="home-search", label_visibility="collapsed"
    )

    rows = []
    for slug, city in configs.items():
        status = statuses[slug]
        if stage != "all" and status["stage"] != stage:
            continue
        if search and search.lower() not in f"{city.name} {city.state}".lower():
            continue
        rows.append(
            {
                "slug": slug,
                "City": city.name,
                "State": city.state,
                "Status": STAGES[status["stage"]][0],
                "Parastatals": "–" if status["parastatals"] is None else status["parastatals"],
                "Citations ready": "–" if status["ready"] is None else status["ready"],
                "Last activity": status["last"].strftime("%d %b %Y") if status["last"] else "",
                "Next step": STAGES[status["stage"]][1],
            }
        )
    if not rows:
        st.caption("No cities match.")
        return
    frame = pd.DataFrame(rows)
    event = st.dataframe(
        frame.drop(columns="slug"),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="home-cities",
        height=min(35 * len(rows) + 45, 420),
    )
    picked = event.selection.rows if event else []
    if not picked:
        st.caption("Select a city to see what you can do next.")
        return
    slug = frame.iloc[picked[0]]["slug"]
    city_actions(slug, configs[slug], statuses[slug])


def city_actions(slug: str, city, status: dict) -> None:
    """The action bar for the selected city."""
    with st.container(border=True):
        st.markdown(
            f"**{city.name}** · {STAGES[status['stage']][0]} · Next: {STAGES[status['stage']][1]}"
        )
        bar = st.container(horizontal=True)
        if status["stage"] == "not_started":
            if bar.button("Find sources", type="primary", icon=":material/travel_explore:"):
                go_to_step("step1", slug)
            return
        if status["stage"] == "answered":
            if bar.button(
                "Open answers",
                type="primary",
                icon=":material/table_view:",
                help="Opens the latest answers workbook in Excel",
            ):
                open_file(status["answers_path"])
        if bar.button(
            "View",
            type="primary" if status["stage"] != "answered" else "secondary",
            icon=":material/visibility:",
            help="See its parastatals, citations and answers here",
        ):
            view_city(city)
        if bar.button("Sources in Excel", icon=":material/edit_document:"):
            open_file(status["sources_path"])
        label = "Answer again" if status["stage"] in {"answered", "changed"} else "Answer"
        if bar.button(label, icon=":material/task_alt:", help="Go to Step 2 for this city"):
            go_to_step("step2", slug)
        if bar.button(
            "Find more sources",
            icon=":material/travel_explore:",
            help="Run Step 1 again for this city",
        ):
            go_to_step("step1", slug)


def view_city(city) -> None:
    """Open the city view (City files) on this city."""
    st.session_state["view-city"] = workspace_for(settings.outputs_dir, city.name).name
    st.switch_page(PAGES["files"])


def go_to_step(page: str, slug: str) -> None:
    """Open Step 1 or Step 2 with this city already selected."""
    st.session_state[f"preselect-{page}"] = [slug]
    st.switch_page(PAGES[page])


def run_title() -> str:
    current = run_store()["current"]
    if current and current.status == "waiting_for_review":
        return "Current run · needs you"
    if current and current.status == "running":
        return "Current run · working"
    return "Current run"


PAGES = {
    "home": st.Page(home_page, title="Home", icon=":material/home:", default=True),
    "step1": st.Page(step1_page, title="Step 1 · Find sources", icon=":material/travel_explore:"),
    "step2": st.Page(step2_page, title="Step 2 · Answer questions", icon=":material/task_alt:"),
    "run": st.Page(run_page, title=run_title(), icon=":material/pending:", url_path="run_page"),
    "files": st.Page(files_page, title="City files", icon=":material/folder_open:"),
    "recheck": st.Page(recheck_page, title="Re-check links", icon=":material/link:"),
    "register": st.Page(register_page, title="City register", icon=":material/location_city:"),
    "setup": st.Page(setup_page, title="Agent setup", icon=":material/psychology:"),
    "checks": st.Page(checks_page, title="Question bank check", icon=":material/rule:"),
    "help": st.Page(help_page, title="Help", icon=":material/help:"),
}
navigation = st.navigation(
    {
        "": [PAGES["home"]],
        "Assess": [PAGES["step1"], PAGES["step2"], PAGES["run"]],
        "Results": [PAGES["files"], PAGES["recheck"]],
        "Settings": [PAGES["register"], PAGES["setup"], PAGES["checks"]],
        "Support": [PAGES["help"]],
    }
)
sidebar_footer()
navigation.run()
