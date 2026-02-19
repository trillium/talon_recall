"""
Recall Core — shims for Talon community actions used by the recall system.

The full dictation/text/keys/formatting stack is provided by exact copies of
community files in core/.  This module only provides the few actions that
recall itself needs but that live outside the copied subset of community.
"""

import os
import subprocess
import sys
from pathlib import Path
from talon import Module, actions, app

mod = Module()


@mod.action_class
class Actions:
    def edit_text_file(file: str):
        """Open a file in the user's preferred text editor (cross-platform)."""
        path = Path(file).resolve()
        if sys.platform == "win32":
            try:
                os.startfile(str(path), "code")
            except OSError:
                os.startfile(str(path), "open")
        elif sys.platform == "darwin":
            subprocess.Popen(["/usr/bin/open", "-t", str(path)])
        else:
            try:
                subprocess.Popen(["xdg-open", str(path)])
            except FileNotFoundError:
                app.notify(f"xdg-open missing. Could not open: {path}")
