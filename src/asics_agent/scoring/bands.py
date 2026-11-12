"""Reading the score bands a question's methodology lists (e.g. "10 — full, 5 — partial")."""

import re

# A band at the start of a line: "10 — ...", "Score 5 if ...", "2.5: ..."
LEVEL = re.compile(r"(?:^|\n)\s*(?:Score\s+)?(\d+(?:\.\d+)?)\s*(?:[—–-]|:|if\b)", re.I)
