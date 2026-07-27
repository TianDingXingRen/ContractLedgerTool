"""Cross-platform subprocess options for background desktop operations."""

import os
import subprocess


def hidden_window_kwargs():
    """Return Popen keyword arguments that suppress Windows console windows."""
    if os.name != 'nt':
        return {}

    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = subprocess.SW_HIDE
    return {
        'creationflags': subprocess.CREATE_NO_WINDOW,
        'startupinfo': startup_info,
    }
