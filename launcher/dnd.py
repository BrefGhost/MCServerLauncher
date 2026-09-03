"""Drag-and-drop for the window, using the tkdnd Tcl extension.

The obvious pure-ctypes route - asking Windows for WM_DROPFILES and subclassing
the window procedure - crashes this Python/Tk build: the callback arrives on a
thread with no Python state and the interpreter aborts. tkdnd plugs into Tk's
own event loop instead, so the drop arrives like any other Tk event.

The package is vendored under `vendor/` so the launcher still works by being
downloaded and run, with nothing to install.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if VENDOR.is_dir() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


def tk_base():
    """The Tk root class to subclass: drop-capable if tkdnd loaded."""
    try:
        from tkinterdnd2 import TkinterDnD
        return TkinterDnD.Tk
    except Exception:
        import tkinter as tk
        return tk.Tk


def enable(widget, on_paths: Callable[[list[str]], None]) -> bool:
    """Accept dropped files/folders on this widget. False if unavailable."""
    try:
        from tkinterdnd2 import DND_FILES
    except Exception:
        return False

    def handle(event) -> None:
        # tkdnd hands over a Tcl list; paths with spaces arrive in braces, and
        # splitlist is the only thing that unpicks them correctly.
        try:
            paths = [str(p) for p in widget.tk.splitlist(event.data)]
        except Exception:
            paths = [event.data]
        on_paths([p for p in paths if p])

    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", handle)
        return True
    except Exception:
        return False
