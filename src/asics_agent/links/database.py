"""The links database: one SQLite file per run, alongside the output workbook."""

import json
import sqlite3
from pathlib import Path

from asics_agent.models import Answer, Issue, Source

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    key TEXT PRIMARY KEY, citation_id TEXT, parastatal_id TEXT, title TEXT, url TEXT,
    source_type TEXT, useful_for TEXT, question_ids TEXT, accessibility TEXT,
    current_status TEXT, verification_status TEXT, authority_score REAL, provenance TEXT,
    found_by TEXT, use_for_answers INTEGER, notes TEXT, content_path TEXT, checked_at TEXT
);
CREATE TABLE IF NOT EXISTS tool_urls (url TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS answers (
    parastatal_id TEXT, question_id TEXT, status TEXT, proposed_score REAL, answer TEXT,
    citation_id TEXT, citation TEXT, citation_url TEXT, evidence_excerpt TEXT, notes TEXT,
    PRIMARY KEY (parastatal_id, question_id)
);
CREATE TABLE IF NOT EXISTS issues (phase TEXT, severity TEXT, message TEXT, ref TEXT);
"""


def write_links_db(
    path: Path,
    sources: list[Source],
    tool_urls: set[str],
    answers: list[Answer] = (),
    issues: list[Issue] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.executemany(
            "INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    s.key,
                    s.citation_id,
                    s.parastatal_id,
                    s.title,
                    s.url,
                    s.source_type,
                    s.useful_for,
                    json.dumps(s.question_ids),
                    s.accessibility,
                    s.current_status,
                    s.verification_status,
                    s.authority_score,
                    s.provenance,
                    s.found_by,
                    int(s.use_for_answers),
                    s.notes,
                    s.content_path,
                    s.checked_at,
                )
                for s in sources
            ],
        )
        db.executemany("INSERT OR IGNORE INTO tool_urls VALUES (?)", [(u,) for u in tool_urls])
        db.executemany(
            "INSERT OR REPLACE INTO answers VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    a.parastatal_id,
                    a.question_id,
                    a.status,
                    a.proposed_score,
                    a.answer,
                    a.citation_id,
                    a.citation,
                    a.citation_url,
                    a.evidence_excerpt,
                    a.notes,
                )
                for a in answers
            ],
        )
        db.execute("DELETE FROM issues")
        db.executemany(
            "INSERT INTO issues VALUES (?,?,?,?)",
            [(i.phase, i.severity, i.message, i.ref) for i in issues],
        )
