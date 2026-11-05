"""Helpers for foreground, application-modal Tkinter windows."""
import tkinter as tk


def activate_modal(window: tk.Toplevel, parent=None):
    """Bring a dialog forward, keep it modal, and allow Escape to close it."""
    try:
        if parent is not None and parent.winfo_exists():
            window.transient(parent)
        window.update_idletasks()
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
        window.grab_set()
        window.bind("<Escape>", lambda _event: window.destroy(), add="+")
        window.after(450, lambda: window.attributes("-topmost", False)
                     if window.winfo_exists() else None)
    except tk.TclError:
        pass
