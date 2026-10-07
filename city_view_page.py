"""The app's city view: everything in a city's workbooks, viewable in the portal.

Read-only: it reads the same Excel files the team edits (the Sources workbook and the answers
workbooks), so what is shown always matches Excel. Editing still happens in Excel.
"""

import html
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from asics_agent.sources_workbook import read_sources_workbook
from asics_agent.workbook import is_scoring_sheet

STATUS_ORDER = [
    ("Answered — Verified Source", "#3E7C4F"),
    ("Computed from Sub-indicators", "#7FB08B"),
    ("Partially Answered", "#D9A441"),
    ("Human Verification Required", "#E07B39"),
    ("Insufficient Evidence", "#C0443A"),
    ("Not Applicable", "#B9B3AB"),
    ("Not Yet Assessed", "#DDD8D0"),
]
VERIFICATION_ICON = {
    "Verified": "✅ Verified",
    "Human Verification Required": "🟠 Needs a person",
    "Not verified": "⛔ Not verified",
}


# -- reading (cached until the file changes) -------------------------------------------------
@st.cache_data(show_spinner=False)
def _read_sheet(path: str, mtime: float, sheet: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
    return frame.dropna(how="all")


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return _read_sheet(str(path), path.stat().st_mtime, sheet)


@st.cache_data(show_spinner=False)
def _sheet_names(path: str, mtime: float) -> list[str]:
    return pd.ExcelFile(path, engine="openpyxl").sheet_names


def sheet_names(path: Path) -> list[str]:
    return _sheet_names(str(path), path.stat().st_mtime)


@st.cache_data(show_spinner=False)
def _citations(path: str, mtime: float, evidence: str):
    parastatals, citations, _ = read_sources_workbook(Path(path), Path(evidence))
    return parastatals, citations


def city_files(folder: Path) -> dict:
    sources = next(folder.glob("ASICS_*_Sources.xlsx"), None)
    answers = sorted(
        (folder / "answers").glob("*/ASICS_Parastatal_*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    rechecks = sorted(
        [*folder.glob("*re-checked*.xlsx"), *(folder / "answers").glob("*/*re-checked*.xlsx")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return {
        "sources": sources,
        "answers": answers,
        "rechecks": rechecks,
        "evidence": folder / "evidence",
    }


def short_ids(frame: pd.DataFrame, parastatals) -> pd.DataFrame:
    """Use parastatal IDs (BWSSB) instead of full names in the Parastatal column."""
    names = {p.name: p.id for p in parastatals}
    if "Parastatal" in frame:
        frame = frame.assign(Parastatal=frame["Parastatal"].map(lambda n: names.get(n, n)))
    return frame


def when(path: Path) -> str:
    return f"{datetime.fromtimestamp(path.stat().st_mtime):%d %b %Y, %H:%M}"


def text(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)


# -- page ------------------------------------------------------------------------------------
def render(folders: list[Path], open_file, zip_folder, header) -> None:
    header(
        "City files",
        "Everything in each city's workbooks, viewable here. To change "
        "anything, open the workbook in Excel.",
        "Results",
    )
    if not folders:
        st.info("Nothing yet. Run Step 1 for a city first.")
        return

    def label(folder: Path) -> str:
        return folder.name + ("  (practice, sample data)" if "practice" in folder.parts else "")

    names = [f.name for f in folders]
    wanted = st.session_state.get("view-city")
    index = names.index(wanted) if wanted in names else 0
    folder = st.selectbox("City", folders, index=index, format_func=label)
    st.session_state["view-city"] = folder.name
    files = city_files(folder)
    if files["sources"] is None:
        st.warning("This city has no Sources workbook yet. Run Step 1 for it.")
        return
    parastatals, citations = _citations(
        str(files["sources"]), files["sources"].stat().st_mtime, str(files["evidence"])
    )

    tabs = st.tabs(["Overview", "Parastatals", "Citation Sheet", "Coverage", "Answers", "Files"])
    with tabs[0]:
        overview(files, parastatals, citations)
    with tabs[1]:
        parastatals_tab(files["sources"])
    with tabs[2]:
        citations_tab(files["sources"], citations, open_file)
    with tabs[3]:
        coverage_tab(files["sources"])
    with tabs[4]:
        answers_tab(files, citations, parastatals, open_file)
    with tabs[5]:
        files_tab(folder, files, open_file, zip_folder)


def overview(files, parastatals, citations) -> None:
    ready = [c for c in citations if c.use_for_answers and c.verification_status == "Verified"]
    coverage = (
        read_sheet(files["sources"], "Coverage")
        if "Coverage" in sheet_names(files["sources"])
        else pd.DataFrame()
    )
    covered = (
        int(coverage["Coverage"].astype(str).str.startswith("Has").sum())
        if "Coverage" in coverage
        else 0
    )
    a, b, c, d = st.columns(4)
    a.metric("Parastatals included", sum(p.include for p in parastatals))
    b.metric("Citations ready", len(ready), help="Verified and marked Use for Answers = Yes")
    c.metric("Questions with a source", f"{covered} of {len(coverage)}")
    d.metric("Answer runs", len(files["answers"]))
    st.caption(f"Sources workbook saved {when(files['sources'])}")

    if not files["answers"]:
        st.info("No answers yet. Review the sources, then run Step 2.")
        return
    latest = files["answers"][0]
    frame = short_ids(answers_frame(latest), parastatals)
    if frame.empty:
        return
    st.markdown(f"**Latest answers** · {when(latest)}")
    counts = frame.groupby(["Parastatal", "Status"]).size().unstack(fill_value=0)
    present = [(s, colour) for s, colour in STATUS_ORDER if s in counts.columns]
    if present:
        st.bar_chart(
            counts[[s for s, _ in present]],
            color=[c for _, c in present],
            horizontal=True,
            height=60 + 45 * len(counts),
        )
    issues = (
        read_sheet(latest, "Needs Attention")
        if "Needs Attention" in sheet_names(latest)
        else pd.DataFrame()
    )
    if not issues.empty and "What we found and what to do" in issues:
        with st.expander(f"Needs attention ({len(issues)})"):
            st.dataframe(issues, hide_index=True, use_container_width=True)


def parastatals_tab(sources: Path) -> None:
    frame = read_sheet(sources, "Parastatals")
    columns = [
        c
        for c in [
            "Parastatal ID",
            "Parastatal Name",
            "Type",
            "Include?",
            "Found By",
            "Official Website",
            "Website Check",
            "Governing Act",
            "Current Status",
            "Why Included",
            "Your Notes",
        ]
        if c in frame
    ]
    st.dataframe(
        frame[columns],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Official Website": st.column_config.LinkColumn(),
            "Website Check": st.column_config.TextColumn(width="large"),
        },
    )


def citations_tab(sources: Path, citations, open_file) -> None:
    frame = read_sheet(sources, "Citation Sheet")
    left, middle, right = st.columns([2, 2, 3])
    owners = sorted(frame["Parastatal"].dropna().astype(str).unique())
    chosen = left.multiselect("Parastatal", owners, placeholder="All")
    status = middle.selectbox(
        "Verification", ["All", "Verified", "Human Verification Required", "Not verified"]
    )
    search = right.text_input("Search", placeholder="Title, link or what it's useful for")
    view = frame
    if chosen:
        view = view[view["Parastatal"].astype(str).isin(chosen)]
    if status != "All":
        view = view[view["Verification Status"] == status]
    if search:
        hay = (
            view[["Source Title", "Official URL", "What This Source Is Useful For"]]
            .astype(str)
            .agg(" ".join, axis=1)
        )
        view = view[hay.str.contains(search, case=False, regex=False)]
    view = view.assign(Verification=view["Verification Status"].map(VERIFICATION_ICON))
    columns = [
        c
        for c in [
            "Citation ID",
            "Parastatal",
            "Source Title",
            "Official URL",
            "Verification",
            "Use for Answers?",
            "Authority Score",
            "Question IDs",
            "Source Type",
        ]
        if c in view
    ]
    st.caption(f"{len(view)} of {len(frame)} citations · click a row to see details")
    event = st.dataframe(
        view[columns],
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="citations",
        height=320,
        column_config={
            "Official URL": st.column_config.LinkColumn("Link", display_text="Open link")
        },
    )
    rows = event.selection.rows if event else []
    if not rows:
        return
    row = view.iloc[rows[0]]
    source = next((c for c in citations if c.citation_id == text(row["Citation ID"])), None)
    with st.container(border=True):
        st.markdown(f"**{text(row['Citation ID'])} · {text(row['Source Title'])}**")
        st.markdown(f"[{text(row['Official URL'])}]({text(row['Official URL'])})")
        st.markdown(f"**Useful for:** {text(row.get('What This Source Is Useful For'))}")
        st.markdown(f"**Notes:** {text(row.get('Notes'))}")
        if text(row.get("Your Notes")):
            st.markdown(f"**Your notes:** {text(row.get('Your Notes'))}")
        saved_copy(source, open_file, key=f"cit-{text(row['Citation ID'])}")
        if source and source.content_path and Path(source.content_path).exists():
            with st.expander("Saved text (as checked)"):
                st.text(Path(source.content_path).read_text(encoding="utf-8")[:4000])


def coverage_tab(sources: Path) -> None:
    if "Coverage" not in sheet_names(sources):
        st.info("This Sources workbook has no Coverage sheet. Run Step 1 again to add it.")
        return
    frame = read_sheet(sources, "Coverage")
    frame = frame.assign(Has=frame["Coverage"].astype(str).str.startswith("Has"))
    missing = frame[~frame["Has"]]
    st.markdown(
        f"**{int(frame['Has'].sum())} of {len(frame)}** question-parastatal pairs have "
        f"at least one source. Questions without one will be answered *Insufficient "
        "Evidence* unless a source is added in Excel."
    )
    grid = frame.pivot_table(
        index="Question ID", columns="Parastatal", values="Has", aggfunc="first"
    )
    grid = grid.map(lambda v: "✓" if v is True else ("—" if v is False else ""))
    st.dataframe(grid, use_container_width=True)
    if not missing.empty:
        with st.expander(f"Questions with no source yet ({len(missing)})"):
            st.dataframe(
                missing[["Parastatal", "Question ID", "Question"]],
                hide_index=True,
                use_container_width=True,
            )


def answers_frame(path: Path) -> pd.DataFrame:
    sheet = next((s for s in sheet_names(path) if is_scoring_sheet(s)), None)
    return read_sheet(path, sheet) if sheet else pd.DataFrame()


def answers_tab(files, citations, parastatals, open_file) -> None:
    if not files["answers"]:
        st.info("No answers yet. Run Step 2 for this city.")
        return
    path = st.selectbox("Answers from", files["answers"], format_func=when)
    frame = short_ids(answers_frame(path), parastatals)
    if frame.empty:
        st.warning("This workbook has no scoring sheet.")
        return
    left, middle, right = st.columns(3)
    owners = sorted(frame["Parastatal"].dropna().astype(str).unique())
    chosen = left.multiselect("Parastatal", owners, placeholder="All", key="ans-p")
    statuses = [s for s, _ in STATUS_ORDER if s in set(frame["Status"].astype(str))]
    status = middle.multiselect("Status", statuses, placeholder="All", key="ans-s")
    section = right.selectbox(
        "Section",
        [
            "All",
            *sorted({str(q).split(" ")[0].split("-")[0] for q in frame["Question ID"].dropna()}),
        ],
        key="ans-sec",
    )
    view = frame
    if chosen:
        view = view[view["Parastatal"].astype(str).isin(chosen)]
    if status:
        view = view[view["Status"].isin(status)]
    if section != "All":
        view = view[view["Question ID"].astype(str).str.startswith(section)]
    view = view.assign(
        Score=[
            f"{text(s)} / {text(m)}" if text(s) else ""
            for s, m in zip(view.get("Proposed Score", []), view.get("Max Score", []), strict=False)
        ]
    )
    columns = [
        c
        for c in [
            "Parastatal",
            "Question ID",
            "Status",
            "Score",
            "Citation ID",
            "Reviewer Decision",
            "Question",
        ]
        if c in view
    ]
    st.caption(f"{len(view)} of {len(frame)} rows · click a row to see the answer and its evidence")
    event = st.dataframe(
        view[columns],
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="answers",
        height=320,
        column_config={"Question": st.column_config.TextColumn(width="large")},
    )
    rows = event.selection.rows if event else []
    if rows:
        answer_detail(view.iloc[rows[0]], citations, open_file)
    if st.button("Open this answers workbook in Excel", icon=":material/table_view:"):
        open_file(path)


def answer_detail(row, citations, open_file) -> None:
    with st.container(border=True):
        st.markdown(
            f"**{text(row['Parastatal'])} · {text(row['Question ID'])}**  \n"
            f"{text(row.get('Question'))}"
        )
        score = text(row.get("Proposed Score"))
        st.markdown(
            f"**Status:** {text(row['Status'])}"
            + (f" · **Score:** {score} / {text(row.get('Max Score'))}" if score else "")
        )
        if text(row.get("Answer")):
            st.markdown(f"**Answer:** {text(row.get('Answer'))}")
        cid = text(row.get("Citation ID"))
        if cid:
            url = text(row.get("Citation URL"))
            st.markdown(f"**Citation:** {cid} · {text(row.get('Citation'))}  \n[{url}]({url})")
            st.markdown(
                f"**Where to find it:** {text(row.get('Where to Find It'))} "
                f"Search for: *{text(row.get('Search Phrase'))}*"
            )
            source = next((c for c in citations if c.citation_id == cid), None)
            quote = text(row.get("Evidence Excerpt"))
            if quote:
                st.markdown("**The quote, in the saved source:**")
                st.markdown(quote_in_context(source, quote), unsafe_allow_html=True)
            saved_copy(source, open_file, key=f"ans-{text(row['Parastatal'])}-{cid}")
        for label, column in [
            ("Notes", "Notes"),
            ("Source needed", "Source Needed"),
            ("Team context used", "Team Context Used"),
            ("Reviewer decision", "Reviewer Decision"),
            ("Reviewer comments", "Reviewer Comments"),
        ]:
            if text(row.get(column)):
                st.markdown(f"**{label}:** {text(row.get(column))}")


def quote_in_context(source, quote: str, around: int = 600) -> str:
    """The quote highlighted inside the surrounding saved text (or on its own)."""
    style = (
        "background:#f6f4f0;border-left:3px solid #110f0f;padding:.7rem .9rem;"
        "border-radius:.4rem;font-size:.92rem;line-height:1.5"
    )
    mark = "<mark style='background:#ffe58a;padding:0 .1rem'>{}</mark>"
    body = ""
    if source and source.content_path and Path(source.content_path).exists():
        full = Path(source.content_path).read_text(encoding="utf-8")
        flat = re.sub(r"\s+", " ", full)
        match = re.search(re.escape(re.sub(r"\s+", " ", quote).strip()), flat, re.I)
        if match:
            start, end = max(0, match.start() - around), min(len(flat), match.end() + around)
            body = (
                "…"
                + html.escape(flat[start : match.start()])
                + mark.format(html.escape(flat[match.start() : match.end()]))
                + html.escape(flat[match.end() : end])
                + "…"
            )
    if not body:
        body = mark.format(html.escape(quote))
    return f"<div style='{style}'>{body}</div>"


def saved_copy(source, open_file, key: str) -> None:
    if source and source.snapshot_path and Path(source.snapshot_path).exists():
        if st.button(
            "Open saved copy",
            key=f"copy-{key}",
            icon=":material/description:",
            help="Opens the page exactly as it was when it was checked",
        ):
            open_file(Path(source.snapshot_path))
    elif source:
        st.caption("No saved copy on this computer; use the link above.")


def files_tab(folder: Path, files, open_file, zip_folder) -> None:
    sources = files["sources"]
    st.markdown(f"**Sources workbook** · saved {when(sources)}")
    a, b = st.columns(2)
    if a.button("Open in Excel", key="open-sources", icon=":material/edit_document:"):
        open_file(sources)
    b.download_button(
        "Download", sources.read_bytes(), sources.name, key="dl-sources", icon=":material/download:"
    )
    if files["answers"]:
        st.markdown("**Answers workbooks**")
        for path in files["answers"][:10]:
            c, d = st.columns(2)
            if c.button(
                f"Open answers from {when(path)}", key=f"open-{path}", icon=":material/table_view:"
            ):
                open_file(path)
            d.download_button(
                "Download",
                path.read_bytes(),
                path.name,
                key=f"dl-{path}",
                icon=":material/download:",
            )
    if files["rechecks"]:
        st.markdown("**Re-checked copies**")
        for path in files["rechecks"][:10]:
            if st.button(f"{path.name}", key=f"open-{path}", icon=":material/link:"):
                open_file(path)
    st.download_button(
        "Download everything for this city (.zip)",
        zip_folder(folder),
        f"ASICS_{folder.name}.zip",
        key=f"zip-{folder}",
        icon=":material/folder_zip:",
    )


def recheck_view(path: Path) -> None:
    """Show a re-checked workbook's results: which links still open, which quotes moved."""
    shown = False
    only_problems = st.toggle("Show only problems", value=True, key=f"probs-{path}")
    for sheet in sheet_names(path):
        frame = read_sheet(path, sheet)
        if "Link Still Opens?" not in frame:
            continue
        shown = True
        frame = frame[frame["Link Still Opens?"].notna()]
        opens = frame["Link Still Opens?"].astype(str).eq("Yes")
        moved = frame.get("Quote Still on Page?", pd.Series(dtype=str)).astype(str)
        moved = moved.str.startswith("No")
        st.markdown(f"**{sheet}**")
        a, b, c = st.columns(3)
        a.metric("Links checked", len(frame))
        b.metric("Still open", int(opens.sum()))
        c.metric("Problems", int((~opens).sum() + moved.sum()))
        view = frame[(~opens) | moved] if only_problems else frame
        if view.empty:
            st.success("No problems in this sheet.")
            continue
        link = "Official URL" if "Official URL" in view else "Citation URL"
        columns = [
            col
            for col in [
                "Citation ID",
                "Parastatal",
                "Question ID",
                "Link Still Opens?",
                "Quote Still on Page?",
                "Source Title",
                link,
                "Link Re-checked On",
            ]
            if col in view
        ]
        st.dataframe(
            view[columns],
            hide_index=True,
            use_container_width=True,
            column_config={
                link: st.column_config.LinkColumn("Link", display_text="Open link"),
                "Link Still Opens?": st.column_config.TextColumn(width="large"),
            },
        )
    if not shown:
        st.info("This workbook has no re-check results.")
