"""Create a fresh city register from the YAML-free defaults below (developer tool).

    uv run python scripts/create_city_register.py [path]

Normally the research team edits data/cities/ASICS_Cities_and_Parastatals.xlsx directly;
use this only to recreate it.
"""

import sys
from pathlib import Path

from asics_agent.cities import write_register
from asics_agent.config import get_settings
from asics_agent.models import CityConfig, Parastatal

CONFIRM = "Confirm this row with the research team."

BENGALURU = CityConfig(
    slug="bengaluru",
    name="Bengaluru",
    state="Karnataka",
    ulg="Greater Bengaluru Authority and its city corporations",
    parastatals=[
        Parastatal(
            id="BWSSB",
            name="Bangalore Water Supply and Sewerage Board",
            type="water_supply_board",
            revenue_raising=True,
            capex_mandate=True,
            notes=CONFIRM,
        ),
        Parastatal(
            id="BMTC",
            name="Bangalore Metropolitan Transport Corporation",
            type="transport_corporation",
            revenue_raising=True,
            capex_mandate=True,
            notes=CONFIRM,
        ),
        Parastatal(
            id="BDA",
            name="Bangalore Development Authority",
            type="development_authority",
            revenue_raising=True,
            capex_mandate=True,
            notes=CONFIRM,
        ),
    ],
)

if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else get_settings().city_register
    if path.exists():
        sys.exit(f"{path} already exists; move it first so the team's edits aren't lost.")
    write_register(
        path, [BENGALURU], {"Bengaluru": "Confirm the current city government structure (ULG)."}
    )
    print(f"Created {path}")
