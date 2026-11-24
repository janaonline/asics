"""Runtime settings, read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from asics_agent.legacy_names import env_category

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def _path(env_var: str, default: str) -> Path:
    path = Path(os.getenv(env_var, default))
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    model: str
    effort: str
    enable_fallbacks: bool
    question_bank: Path
    city_register: Path
    agent_setup_dir: Path
    category: str
    memory_max_chars: int
    outputs_dir: Path
    max_concurrency: int
    check_workers: int
    http_timeout: float
    llm_call_timeout: float
    api_read_timeout: float
    user_agent: str
    max_evidence_chars: int
    assess_evidence_chars: int  # Step 1: page text the source assessor reads
    batch_answers: bool  # Step 2: send model calls as Message Batches (half price, slower)
    batch_live_up_to: int  # Step 2: a round with this many calls or fewer is sent live
    scoring_dir: Path = PROJECT_ROOT / "scoring" / "2027"  # templates, human/AI copies, results
    # The category being run (agent_setup/categories/<category>.md; see categories.py). The
    # defaults are the Parastatal category's.
    category_title: str = "Parastatal"
    scoring_code: str = "PARASTATAL"  # the scoring workbook's code (file and sheet names)
    unit: str = "parastatal"  # what is assessed: "parastatal" or "ulg"
    unit_label: str = "Parastatal"
    shared_rules: str = "shared-rules"
    agents: tuple = ()  # (role, agent name) pairs that differ from the defaults
    question_bank_sheet: str = ""
    question_columns: tuple = ()  # (our column name, the bank's column name) pairs
    scoring_workbook: Path | None = None
    scoring_templates: tuple = ()  # the team's templates, one per section (see categories.py)
    # Law/Policy questions may only use sources that took effect on or before this date (None =
    # no cut-off), and what to do with a source whose date is unknown: "confirm" or "block".
    law_cutoff: date | None = None
    undated_law_policy: str = "confirm"
    # A score of 0 needs the sources the question requires (agent_setup/categories/<name>.md,
    # `required_sources: on`; see source_requirements.py). Off for a category that does not say so.
    required_sources: bool = False
    human_verified_sources: bool = False  # see categories.py (agent_setup/categories/<name>.md)
    crawl_max_pages: int = 0  # Step 1: menu links of an agency's home page to open (0 = no crawl)
    crawl_incomplete_on_dead_link: str = "strict"  # or "lenient" (see links/crawl.py)
    outputs_root: Path | None = None  # the outputs folder before the category's subfolder
    # Searches/fetches per source-finding call (Step 1). None = the agent's own max_uses.
    find_sources_max_uses: int | None = None
    # The staged fetch (links/fetch_chain.py): plain HTTP, then retries and address variants, then a
    # Chromium render, then the Wayback Machine. Off = the plain check only (the earlier behaviour).
    staged_fetch: bool = True
    # An archived copy older than this is "stale archive" and is not used (days).
    archive_max_age_days: int = 365
    # A URL that failed the whole chain is not retried for this many hours (0 = always retry).
    failure_cache_hours: float = 24.0
    # The chain's time cap in one run, in minutes (0 = none); past it links get the plain check only.
    fetch_time_cap_minutes: float = 20.0


@lru_cache
def get_settings() -> Settings:
    """Settings for the category named by ASICS_CATEGORY (default: parastatal)."""
    from asics_agent.categories import category_settings

    base = _base_settings()
    return category_settings(base, base.category)


def _base_settings() -> Settings:
    return Settings(
        model=os.getenv("ASICS_MODEL", "claude-sonnet-5-5"),
        effort=os.getenv("ASICS_EFFORT", "medium"),
        enable_fallbacks=os.getenv("ASICS_ENABLE_FALLBACKS", "true").lower() == "true",
        question_bank=_path(
            "ASICS_QUESTION_BANK", "data/question_banks/Parastatal_ASICS_Question_Bank.xlsx"
        ),
        city_register=_path("ASICS_CITY_REGISTER", "data/cities/ASICS_Cities_and_Parastatals.xlsx"),
        outputs_dir=_path("ASICS_OUTPUTS_DIR", "outputs"),
        agent_setup_dir=_path("ASICS_AGENT_SETUP_DIR", "agent_setup"),
        category=env_category(),
        memory_max_chars=int(os.getenv("ASICS_MEMORY_MAX_CHARS", "20000")),
        max_concurrency=int(os.getenv("ASICS_MAX_CONCURRENCY", "4")),
        check_workers=int(os.getenv("ASICS_CHECK_WORKERS", "3")),
        http_timeout=float(os.getenv("ASICS_HTTP_TIMEOUT", "30")),
        llm_call_timeout=float(os.getenv("ASICS_LLM_CALL_TIMEOUT", "900")),
        api_read_timeout=float(os.getenv("ASICS_API_READ_TIMEOUT", "300")),
        # A browser-like agent that also names this tool, so a site's owner can tell who is reading.
        user_agent=os.getenv(
            "ASICS_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36 ASICS-link-check/1.0",
        ),
        find_sources_max_uses=int(os.getenv("ASICS_FIND_SOURCES_MAX_USES") or 0) or None,
        max_evidence_chars=int(os.getenv("ASICS_MAX_EVIDENCE_CHARS", "60000")),
        assess_evidence_chars=int(os.getenv("ASICS_ASSESS_EVIDENCE_CHARS", "15000")),
        batch_answers=os.getenv("ASICS_STEP2_BATCH", "true").strip().lower()
        not in ("0", "false", "no", "off"),
        batch_live_up_to=int(os.getenv("ASICS_STEP2_BATCH_LIVE_UP_TO", "5")),
        scoring_dir=_path("ASICS_SCORING_DIR", "scoring/2027"),
    )
