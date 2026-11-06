"""LangGraph agents for Janaagraha's ASICS assessment work."""

import warnings

# The team's templates keep the "Parastatal Name" drop-down as an Excel x14 extension, which openpyxl
# cannot read: it warns on every open. Reading loses nothing, and saving a copy puts the drop-down
# back (scoring/template_fill.py), so this one message is not worth showing.
warnings.filterwarnings(
    "ignore", message="Data Validation extension is not supported", category=UserWarning
)
