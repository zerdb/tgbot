"""Helpers for foreground, application-modal Tkinter windows."""
import tkinter as tk


def activate_modal(window: tk.Toplevel, parent=None):
    """Bring a dialog forward, focus it, and keep interaction inside it."""
    try:
        if parent is not None and parent.winfo_exists():
            window.transient(parent)
        window.update_idletasks()
        # Brief topmost promotion helps Windows surface dialogs opened by voice.
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
        window.grab_set()
        window.after(450, lambda: window.attributes("-topmost", False)
                     if window.winfo_exists() else None)
    except tk.TclError:
        pass
