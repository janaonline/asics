"""Runtime settings, read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

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
    vertical: str
    memory_max_chars: int
    outputs_dir: Path
    max_concurrency: int
    check_workers: int
    web_search_max_uses: int
    http_timeout: float
    llm_call_timeout: float
    user_agent: str
    max_evidence_chars: int
    scoring_dir: Path = PROJECT_ROOT / "scoring" / "2027"  # templates, human/AI copies, results
    # The vertical being run (agent_setup/verticals/<vertical>.md; see verticals.py). The
    # defaults are the Parastatal vertical's.
    vertical_title: str = "Parastatal"
    vertical_code: str = "PARASTATAL"
    unit: str = "parastatal"  # what is assessed: "parastatal" or "city_government"
    unit_label: str = "Parastatal"
    shared_rules: str = "shared-rules"
    agents: tuple = ()  # (role, agent name) pairs that differ from the defaults
    question_bank_sheet: str = ""
    question_columns: tuple = ()  # (our column name, the bank's column name) pairs
    scoring_workbook: Path | None = None
    outputs_root: Path | None = None  # the outputs folder before the vertical's subfolder


@lru_cache
def get_settings() -> Settings:
    """Settings for the vertical named by ASICS_VERTICAL (default: parastatal)."""
    from asics_agent.verticals import settings_for

    base = _base_settings()
    return settings_for(base, base.vertical)


def _base_settings() -> Settings:
    return Settings(
        model=os.getenv("ASICS_MODEL", "claude-opus-5-5"),
        effort=os.getenv("ASICS_EFFORT", "high"),
        enable_fallbacks=os.getenv("ASICS_ENABLE_FALLBACKS", "true").lower() == "true",
        question_bank=_path(
            "ASICS_QUESTION_BANK", "data/question_banks/Parastatal_ASICS_Question_Bank.xlsx"
        ),
        city_register=_path("ASICS_CITY_REGISTER", "data/cities/ASICS_Cities_and_Parastatals.xlsx"),
        outputs_dir=_path("ASICS_OUTPUTS_DIR", "outputs"),
        agent_setup_dir=_path("ASICS_AGENT_SETUP_DIR", "agent_setup"),
        vertical=os.getenv("ASICS_VERTICAL", "parastatal"),
        memory_max_chars=int(os.getenv("ASICS_MEMORY_MAX_CHARS", "20000")),
        max_concurrency=int(os.getenv("ASICS_MAX_CONCURRENCY", "4")),
        check_workers=int(os.getenv("ASICS_CHECK_WORKERS", "3")),
        web_search_max_uses=int(os.getenv("ASICS_WEB_SEARCH_MAX_USES", "8")),
        http_timeout=float(os.getenv("ASICS_HTTP_TIMEOUT", "30")),
        llm_call_timeout=float(os.getenv("ASICS_LLM_CALL_TIMEOUT", "900")),
        user_agent=os.getenv(
            "ASICS_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
        ),
        max_evidence_chars=int(os.getenv("ASICS_MAX_EVIDENCE_CHARS", "60000")),
        scoring_dir=_path("ASICS_SCORING_DIR", "scoring/2027"),
    )
