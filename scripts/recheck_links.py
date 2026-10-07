"""Re-check every link in a finished workbook.

uv run python scripts/recheck_links.py "path/to/workbook.xlsx"
"""

import sys
from pathlib import Path

from asics_agent.config import get_settings
from asics_agent.links.accessibility import make_http_client
from asics_agent.recheck import recheck_workbook, summary_text

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    settings = get_settings()
    out, summary = recheck_workbook(
        Path(sys.argv[1]),
        make_http_client(settings.user_agent, settings.http_timeout),
        settings.user_agent,
    )
    print(summary_text(summary))
    print(f"Saved: {out}")
