"""Stop the computer from going to sleep while a run is working.

A sleeping Mac freezes the run, and the connections to Claude it had open are dropped; a
run once showed "3 of 7 parastatals finished" for over two hours because the laptop kept
idle-sleeping on battery. Closing the lid still sleeps the computer.
"""

import contextlib
import os
import shutil
import subprocess
import sys

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def keep_awake():
    """Prevent idle sleep inside the `with` block. Does nothing where unsupported."""
    if sys.platform == "darwin" and (caffeinate := shutil.which("caffeinate")):
        # -i: no idle sleep (works on battery); -w: exits by itself if the app dies.
        process = subprocess.Popen([caffeinate, "-i", "-w", str(os.getpid())])
        try:
            yield
        finally:
            process.terminate()
    elif sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        try:
            yield
        finally:
            kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    else:
        yield
