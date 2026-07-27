import os
import subprocess

from utils.subprocess_utils import hidden_window_kwargs


def test_hidden_window_kwargs_match_current_platform():
    kwargs = hidden_window_kwargs()
    if os.name != 'nt':
        assert kwargs == {}
        return

    assert kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW
    startup_info = kwargs['startupinfo']
    assert startup_info.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startup_info.wShowWindow == subprocess.SW_HIDE
