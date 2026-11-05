"""Step 3 · People's scoring for a category scored in the team's templates (Parastatal).

Upload the filled templates (drag and drop), check each one in a preview, and press Save to store
it as an immutable submission. Merge and calculate builds the merged people's workbook from the
stored submissions; the Scores page reads that file. Nothing here needs Excel on this computer:
every file can be downloaded. The assignments workbook and the interns' copies are under the last
heading.
"""

import dataclasses
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from asics_agent.cities import TYPES, load_register
from asics_agent.hosting import can_open
from asics_agent.parastatal_types import canonical_type, known_type
from asics_agent.scoring import (
    human_copies,
    human_merge,
    name_resolution,
    register_edit,
    submissions,
    workflow,
)
from asics_agent.scoring.name_resolution import Decision, norm_name

SHOW = 12  # lines of a long list shown before "and N more"


def _practice_settings(settings):
    from compare_page import _practice_settings

    return _practice_settings(settings)


@st.cache_data(show_spinner="Reading the file…", max_entries=24)
def _preview(
    scoring_dir: str,
    category: str,
    section: str,
    name: str,
    sha: str,
    stored: int,
    _settings,
    _data,
):
    return submissions.preview_file(_settings, section, name, _data)


def render(settings, open_file) -> None:
    st.markdown("#### People's scoring")
    st.caption(
        f"People score in the team's {settings.category_title} templates (the same ones the AI "
        "fills). Upload each filled file here: it is checked, then stored as it is and never "
        "changed. **Merge and calculate** builds the people's workbook the Scores page compares "
        "with the AI's."
    )
    if (settings.scoring_dir / "practice").exists() and st.toggle(
        "Practice (sample cities: uploads and merges go to the practice folder)",
        key="people-practice",
    ):
        settings = _practice_settings(settings)
    sections = list(submissions.section_templates(settings))
    if not sections:
        st.warning(
            f"None of the scoring templates in {settings.category_title}'s settings could be "
            "read, so nothing can be uploaded.",
            icon=":material/warning:",
        )
        return
    section = st.segmented_control("Section", sections, default=sections[0], key="people-section")
    section = section or sections[0]
    _upload(settings, section)
    _stored(settings, section, open_file)
    _names_to_add(settings)
    _merge(settings, open_file)
    _assignments(settings, open_file)


# -- upload and preview ---------------------------------------------------------------------
def _upload(settings, section: str) -> None:
    st.markdown(f"##### Upload {section} files")
    left, right = st.columns(2)
    scorer = left.text_input(
        "Scorer's name",
        key="people-scorer",
        help="Who filled the file in. It is typed here, not taken from the file name.",
    )
    uploader = right.text_input(
        "Uploaded by (your name)",
        key="people-uploader",
        placeholder="Leave empty if it is the scorer",
    )
    files = st.file_uploader(
        f"Filled {section} template(s)",
        type=["xlsx"],
        accept_multiple_files=True,
        key=f"people-files-{section}",
        help="Excel workbooks (.xlsx) only; files with macros are refused.",
    )
    if not files:
        st.caption(
            "Nothing is stored until you press Save. A file already stored (the same file) is "
            "recognised and not stored twice."
        )
        return
    previews = []
    for f in files:
        data = f.getvalue()
        sha = submissions.sha256_of(data)
        preview = _preview(
            str(settings.scoring_dir),
            settings.category,
            section,
            f.name,
            sha,
            len(submissions.list_submissions(settings)),
            settings,
            data,
        )
        found = submissions.find_by_hash(settings, sha)
        preview = dataclasses.replace(preview, duplicate_of=found.submission_id if found else "")
        previews.append((f, data, preview))
    saveable = [x for x in previews if x[2].can_save]
    for i, (_, data, preview) in enumerate(previews):
        _show_preview(settings, preview, data, scorer, uploader, f"people-{section}-{i}")
    if len(saveable) > 1 and st.button(
        f"Save all {len(saveable)} files that can be saved",
        icon=":material/save:",
        disabled=not scorer.strip(),
        key=f"people-all-{section}",
    ):
        for _, data, preview in saveable:
            decisions, complete, aliases = _resolution_table(
                settings, preview, f"res-{preview.sha256[:8]}", show=False
            )
            if complete:
                _save(settings, preview, data, scorer, uploader, decisions, aliases)
        st.rerun()
    if not scorer.strip():
        st.caption("Type the scorer's name to enable Save.")


def _lines(title: str, items: list[str], icon: str = "") -> None:
    if not items:
        return
    st.markdown(f"**{title}** ({len(items)})")
    for line in items[:SHOW]:
        st.markdown(f"- {line}")
    if len(items) > SHOW:
        with st.popover(f"and {len(items) - SHOW} more"):
            for line in items[SHOW:]:
                st.markdown(f"- {line}")


def _show_preview(settings, p, data: bytes, scorer: str, uploader: str, key: str) -> None:
    mark = (
        "❌"
        if p.errors
        else "♻️"
        if p.duplicate_of
        else "⚠️"
        if p.issue_count or p.warnings
        else "✅"
    )
    with st.container(border=True):
        st.markdown(f"{mark} **{p.name}** · {p.size / 1024:.0f} KB")
        for error in p.errors:
            st.error(error, icon=":material/block:")
        if p.errors:
            return
        if p.duplicate_of:
            st.info(
                f"This exact file is already stored ({p.duplicate_of}). Nothing was added.",
                icon=":material/content_copy:",
            )
        cols = st.columns(5)
        cols[0].metric(
            "Template", p.template.replace("Parastatal_", "").replace("_Template.xlsx", "")
        )
        cols[1].metric("Sheets read", len(p.sheets_read))
        cols[2].metric("Rows read", p.rows_read)
        cols[3].metric("Rows with a score", p.rows_with_score)
        cols[4].metric("Issues", p.issue_count)
        st.caption(
            f"Matches {p.template} · question bank in use {p.bank_version or 'unknown'} · "
            f"scorer named in the file: {', '.join(p.scorers_in_file) or '–'} (the typed name is used)"
        )
        for warning in p.warnings:
            st.warning(warning, icon=":material/warning:")
        _lines(
            "Formula cells with no saved value: open the file in Excel and save it first",
            p.formula_no_value,
        )
        _lines("Retired or changed questions (kept as they are, flagged)", p.retired_or_changed)
        _lines("Values the template does not allow", p.not_allowed)
        _lines("Cities or parastatals not in the register", p.not_in_register)
        _lines("Rows and sheets that were not read", p.ignored)
        _lines("Other things the reader noticed", p.other)
        decisions, complete, aliases = _resolution_table(settings, p, f"res-{p.sha256[:8]}")
        if p.can_save and not complete:
            st.caption("Choose what to do with every city and parastatal above to enable Save.")
        if p.can_save and st.button(
            "Save and update the register" if aliases else "Save this file",
            key=f"{key}-save",
            icon=":material/save:",
            type="primary",
            disabled=not scorer.strip() or not complete,
            help="Stores the file as it is, under the scorer's name, with your choices about names",
        ):
            if _save(settings, p, data, scorer, uploader, decisions, aliases):
                st.rerun()


def _save(settings, preview, data, scorer, uploader, decisions=(), aliases=()) -> bool:
    for kind, city, alias, code in aliases:  # "Other names" the person chose to add to the register
        error = register_edit.add_other_name(settings, kind, city, alias, code)
        if error:
            st.error(f'"{alias}" was not added to the register: {error}', icon=":material/error:")
        else:
            for d in decisions:
                if d.kind == kind and d.as_written == alias:
                    d.other_name_in_register = True
    if aliases:
        st.cache_data.clear()
    try:
        sub = submissions.save_submission(
            settings, preview, data, scorer, uploader, list(decisions)
        )
    except submissions.SubmissionError as exc:
        st.error(str(exc), icon=":material/error:")
        return False
    st.toast(f"Saved {sub.original_name} as {sub.submission_id}", icon="✅")
    return True


# -- the cities and parastatals of an upload ------------------------------------------------------
CHOOSE, MAP, NEW, SKIP = "Choose…", "Map to existing", "Add as new", "Skip"
ACTION_OF = {MAP: "map", NEW: "new", SKIP: "skip"}
LABEL_OF = {v: k for k, v in ACTION_OF.items()}


def _match_text(r) -> str:
    kinds = {
        "exact": "in the register",
        "alias": "an Other name of",
        "close": "close to",
        "none": "",
    }
    if r.match.kind == "none":
        return "no match in the register"
    return f"{kinds[r.match.kind]} {r.match.name}".strip()


def _resolution_table(settings, p, key: str, show: bool = True):
    """The "Cities and parastatals" table: each name as written in the file, the register's match,
    and a choice (earlier decisions pre-fill it). Returns (decisions, all decided, Other names to
    write into the register)."""
    rs = p.resolutions
    if not rs:
        return [], True, []
    register, _ = load_register(settings.city_register)
    cities = {c.name: c for c in register.values()}
    by_slug = {c.slug: c for c in register.values()}
    decisions: list[Decision] = []
    aliases: list[tuple] = []
    complete = True
    mapped_city: dict[str, str] = {}  # norm city as written -> register slug
    skipped_city: set[str] = set()
    if show:
        st.markdown("**Cities and parastatals**")
        st.caption(
            "Names as written in the file and the register's match. Where a name is not in the "
            "register, choose: map it to an existing one, add it as new (kept in people's scoring "
            "only: the AI cannot score it until the register has it) or skip its rows. Choices "
            "from earlier uploads are filled in; change them if they are wrong."
        )
    for i, r in enumerate(rs):
        city_key = norm_name(r.as_written if r.kind == "city" else r.city_as_written)
        if not r.needs_decision:
            if r.kind == "city":
                mapped_city[city_key] = r.match.slug
            if show:
                a, b = st.columns([3, 5])
                a.write(
                    f"{r.as_written}"
                    + (f" ({r.city_as_written})" if r.kind == "parastatal" else "")
                )
                b.caption(f"✅ {_match_text(r)} · {r.rows} row(s)")
            continue
        if r.kind == "parastatal" and city_key in skipped_city:
            if show:
                a, b = st.columns([3, 5])
                a.write(f"{r.as_written} ({r.city_as_written})")
                b.caption("⏭️ skipped with its city")
            continue
        old = r.remembered
        guess = None
        if old is not None:
            guess = LABEL_OF[old.action]
        elif r.match.kind == "close":
            guess = MAP
        options = [CHOOSE, MAP, NEW, SKIP]
        a, b, c = st.columns([3, 4, 5]) if show else (st.container(),) * 3
        label = r.as_written + (f" ({r.city_as_written})" if r.kind == "parastatal" else "")
        if show:
            a.write(f"**{label}** · {r.rows} row(s)")
            b.caption(
                f"⚠️ {_match_text(r)}"
                + (f" · remembered from {old.submission_id}" if old is not None else "")
            )
        choice = (
            c.selectbox(
                "What to do",
                options,
                index=options.index(guess) if guess else 0,
                key=f"{key}-{i}-act",
                label_visibility="collapsed",
            )
            if show
            else (st.session_state.get(f"{key}-{i}-act") or guess or CHOOSE)
        )
        action = ACTION_OF.get(choice)
        if action is None:
            complete = False
            continue
        d = Decision(
            r.kind, r.as_written, action, r.city_as_written if r.kind == "parastatal" else ""
        )
        if action == "map":
            ok = _map_fields(
                settings, r, d, c, key, i, cities, by_slug, mapped_city, old, aliases, show
            )
            complete = complete and ok
            if r.kind == "city" and d.city_slug:
                mapped_city[city_key] = d.city_slug
        elif action == "new":
            ok = _new_fields(r, d, c, key, i, old, show)
            complete = complete and ok
        if action == "skip" and r.kind == "city":
            skipped_city.add(city_key)
        decisions.append(d)
    return decisions, complete, aliases


def _map_fields(
    settings, r, d, col, key, i, cities, by_slug, mapped_city, old, aliases, show
) -> bool:
    from asics_agent.scoring.compare_run import city_units

    if r.kind == "city":
        names = list(cities)
        default = old.city_slug if old else r.match.slug
        current = next((c.name for c in cities.values() if c.slug == default), None)
        pick = (
            col.selectbox(
                "Map to",
                names,
                index=names.index(current) if current in names else None,
                placeholder="Choose a city",
                key=f"{key}-{i}-tgt",
            )
            if show
            else st.session_state.get(f"{key}-{i}-tgt") or current
        )
        if not pick:
            return False
        d.city_slug = cities[pick].slug
        target_name = pick
    else:
        slug = mapped_city.get(norm_name(r.city_as_written))
        if slug not in by_slug:
            if show:
                col.caption("Its city is not in the register: map the city first, or add as new.")
            return False
        city = by_slug[slug]
        units = city_units(settings, city)[0]
        codes = list(units)
        suggested = name_resolution.match_unit(units, r.as_written)
        default = old.parastatal_code if old and old.parastatal_code in units else suggested.slug
        pick = (
            col.selectbox(
                "Map to",
                codes,
                index=codes.index(default) if default in codes else None,
                placeholder="Choose a parastatal",
                format_func=lambda c: f"{c} · {units[c].name}",
                key=f"{key}-{i}-tgt",
            )
            if show
            else st.session_state.get(f"{key}-{i}-tgt") or default
        )
        if not pick:
            return False
        d.city_slug, d.parastatal_code = slug, pick
        target_name = city.name
    write = (
        col.checkbox(
            f'Also add "{r.as_written}" as an Other name in the register',
            key=f"{key}-{i}-alias",
            help="Edits one cell of the register file; a copy is kept in data/cities/history/ first.",
        )
        if show
        else bool(st.session_state.get(f"{key}-{i}-alias"))
    )
    if write:
        aliases.append(
            (r.kind, target_name, r.as_written, d.parastatal_code if r.kind == "parastatal" else "")
        )
    return True


def _new_fields(r, d, col, key, i, old, show) -> bool:
    if r.kind == "city":
        state = (
            col.text_input(
                "State (required)", value=old.state if old else "", key=f"{key}-{i}-state"
            )
            if show
            else st.session_state.get(f"{key}-{i}-state", old.state if old else "")
        )
        ulg = (
            col.text_input(
                "City government (optional)", value=old.ulg if old else "", key=f"{key}-{i}-ulg"
            )
            if show
            else st.session_state.get(f"{key}-{i}-ulg", old.ulg if old else "")
        )
        d.state, d.ulg = state.strip(), ulg.strip()
        d.city_slug = name_resolution.slugify(r.as_written)
        return bool(d.state)
    labels = list(TYPES)
    from_file = r.type_from_file if known_type(r.type_from_file) else ""
    code = old.type if old and old.type else canonical_type(from_file) if from_file else ""
    current = next((label for label, c in TYPES.items() if c == code), None)
    code_text = (
        col.text_input(
            "Short code",
            value=old.parastatal_code if old and old.parastatal_code else r.as_written,
            key=f"{key}-{i}-code",
        )
        if show
        else st.session_state.get(f"{key}-{i}-code", r.as_written)
    )
    pick = (
        col.selectbox(
            "Type (required)",
            labels,
            index=labels.index(current) if current in labels else None,
            placeholder="Choose a type" + (" (the file gives none)" if not from_file else ""),
            key=f"{key}-{i}-type",
        )
        if show
        else st.session_state.get(f"{key}-{i}-type") or current
    )
    d.parastatal_code = code_text.strip() or r.as_written
    d.type = TYPES.get(pick, "")
    return bool(d.type)


# -- what is stored -------------------------------------------------------------------------
def _stored(settings, section: str, open_file) -> None:
    items = submissions.list_submissions(settings, section)
    st.markdown(f"##### Stored {section} files ({len(items)})")
    if not items:
        st.caption("None yet.")
        return
    frame = pd.DataFrame(
        [
            {
                "Scorer": s.scorer,
                "Uploaded": _when(s.uploaded_at),
                "Uploaded by": s.uploaded_by,
                "Rows with a score": s.rows_with_score,
                "Issues": s.issue_count,
                "Replaces earlier files of the scorer": "Yes" if s.replaces else "",
                "Bank": s.bank_version,
                "ID": s.submission_id,
            }
            for s in reversed(items)
        ]
    )
    st.dataframe(frame, hide_index=True, width="stretch", height=min(360, 40 + 35 * len(items)))
    with st.expander("Download a stored file"):
        for s in reversed(items):
            row = st.container(horizontal=True, vertical_alignment="center")
            row.write(f"{s.scorer} · {_when(s.uploaded_at)} · {s.original_name}")
            if s.path and s.path.exists():
                row.download_button(
                    "Download",
                    s.path.read_bytes(),
                    file_name=s.file_name,
                    key=f"dl-sub-{s.submission_id}",
                    icon=":material/download:",
                )
                if can_open(open_file) and row.button(
                    "Open", key=f"open-sub-{s.submission_id}", icon=":material/table_view:"
                ):
                    open_file(s.path)
            else:
                row.caption("The stored file is missing.")


def _names_to_add(settings) -> None:
    rows = register_edit.names_to_add(settings)
    with st.expander(f"Names to add to the register ({len(rows)})", icon=":material/playlist_add:"):
        st.caption(
            "Cities and parastatals people scored that the register does not have, and names "
            "that could be an Other name. The research lead adds them to the register by hand "
            "(the AI cannot score them until then)."
        )
        if not rows:
            st.caption("Nothing to add.")
            return
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.download_button(
            "Download as CSV",
            register_edit.names_csv(rows).encode("utf-8-sig"),
            file_name="names_to_add_to_the_register.csv",
            mime="text/csv",
            key="dl-names-to-add",
            icon=":material/download:",
        )


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d %b %Y %H:%M")
    except ValueError:
        return iso


# -- merge ----------------------------------------------------------------------------------
def _merge(settings, open_file) -> None:
    from scoring_page import show_report

    st.markdown("##### Merge and calculate")
    waiting = human_merge.newer_than_merge(settings)
    st.caption(
        "Builds each section's people's workbook from the stored files, as often as you like. "
        "A blank never overwrites a value; two scorers who disagree are listed below and the "
        "row stays blank until they agree."
        + (f" **{len(waiting)} stored file(s) are not merged yet.**" if waiting else "")
    )
    if st.button("Merge and calculate", icon=":material/calculate:", key="people-merge"):
        with st.spinner("Merging and calculating (a few seconds per section)…"):
            st.session_state["people-report"] = workflow.merge_templates(settings)
        st.cache_data.clear()
    report = st.session_state.get("people-report")
    if report:
        st.markdown(f"###### {report.title}")
        show_report(report, open_file, key="people-merge-report")
    else:
        for path in human_merge.merged_files(settings):
            row = st.container(horizontal=True, vertical_alignment="center")
            row.write(path.name)
            row.download_button(
                "Download",
                path.read_bytes(),
                file_name=path.name,
                key=f"dl-merged-{path.name}",
                icon=":material/download:",
            )
            if can_open(open_file) and row.button(
                "Open", key=f"open-merged-{path.name}", icon=":material/table_view:"
            ):
                open_file(path)
    _needs_a_look(settings)


def _needs_a_look(settings) -> None:
    found = human_merge.conflicts(settings)
    extra = [
        line
        for path in human_merge.merged_files(settings)
        for line in human_merge.read_merge_info(path).get("incomplete", [])
    ]
    if not found and not extra:
        return
    with st.container(border=True):
        st.markdown(f"**Needs a look from the last merge ({len(found) + len(extra)})**")
        if found:
            st.caption(
                "Two scorers gave different values for the same question and row. Nothing was "
                "chosen for them: the row is blank in the merged workbook until they agree. "
                "Upload a corrected file and merge again."
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Question": c.code,
                            "City": c.city,
                            "Parastatal": c.unit or "ULG",
                            "Field": c.field,
                            **{
                                f"{e['scorer']}": f"{e['value']}"
                                + (f" · {e['source']}" if e["source"] else "")
                                for e in c.entries
                            },
                        }
                        for c in found
                    ]
                ).fillna(""),
                hide_index=True,
                width="stretch",
            )
        for line in extra:
            st.markdown(f"- {line}")


# -- the assignments workbook and the interns' copies ------------------------------------------
def _assignments(settings, open_file) -> None:
    from scoring_page import show_report

    with st.expander("Assignments and interns' copies", icon=":material/assignment_ind:"):
        st.markdown(
            "Optional: say who scores which questions for which cities, and give each intern a "
            "copy of the template with those rows ready and a **Step 2 evidence** sheet. They "
            "fill it in, save it as .xlsx and send it back; upload it above."
        )
        path = workflow.assignments_path(settings)
        row = st.container(horizontal=True, vertical_alignment="center")
        row.download_button(
            "Download the assignments workbook",
            path.read_bytes(),
            file_name=path.name,
            key="dl-assignments",
            icon=":material/download:",
        )
        if can_open(open_file) and row.button(
            "Open it in Excel", key="open-assignments", icon=":material/assignment_ind:"
        ):
            open_file(path)
        st.caption(
            f"Put **{settings.scoring_code}** in the Category column of its Assignments sheet; "
            'questions like "UPD*", "SC 1" or "DPG 5*"; cities by name or "All".'
        )
        new = st.file_uploader(
            "Replace it with your edited copy",
            type=["xlsx"],
            key="people-assignments-up",
            help="The workbook it replaces is kept in assignments/history.",
        )
        if new is not None and st.button("Use this assignments workbook", key="people-use"):
            error = human_copies.replace_assignments(settings, new.getvalue(), new.name)
            (st.error if error else st.success)(
                error or "The assignments workbook was replaced (the old one is kept)."
            )
        row = st.container(horizontal=True)
        if row.button("Check", icon=":material/rule:", key="people-check"):
            with st.spinner("Checking…"):
                st.session_state["people-copies"] = workflow.check(settings)
        if row.button("Make interns' copies", icon=":material/content_copy:", key="people-copy"):
            with st.spinner("Making copies (a few seconds each)…"):
                st.session_state["people-copies"] = workflow.prepare_templates(settings)
        if report := st.session_state.get("people-copies"):
            st.markdown(f"###### {report.title}")
            show_report(report, open_file, key="people-copies-report")
        copies = sorted(
            p for s in submissions.section_templates(settings) for p in _copies(settings, s)
        )
        for copy in copies:
            row = st.container(horizontal=True, vertical_alignment="center")
            row.write(f"{copy.parent.parent.name} · {copy.name}")
            row.download_button(
                "Download",
                copy.read_bytes(),
                file_name=f"{copy.parent.parent.name}_{copy.name}",
                key=f"dl-copy-{copy.parent.parent.name}-{copy.name}",
                icon=":material/download:",
            )


def _copies(settings, section: str) -> list[Path]:
    folder = submissions.copies_dir(settings, section)
    return sorted(folder.glob("*.xlsx")) if folder.exists() else []
