"""Whether the app runs on the user's own computer or on a server.

On a server the app cannot open a file in the user's Excel, so pages offer a download instead
(they always offer one). Set ASICS_HOSTED=1 on the server to hide the "Open" buttons.
"""

import os


def hosted() -> bool:
    return os.getenv("ASICS_HOSTED", "").strip().lower() in {"1", "true", "yes"}


def can_open(open_file) -> bool:
    """True when a function that opens a file on this computer is given and makes sense here."""
    return bool(open_file) and not hosted()
