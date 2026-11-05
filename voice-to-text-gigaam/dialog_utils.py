"""Helpers for centered, foreground Tkinter windows."""
import tkinter as tk

def center_window(window: tk.Misc, parent=None):
    """Center a window on the screen after its requested size is calculated."""
    try:
        window.update_idletasks()
        width=window.winfo_width() if window.winfo_width()>1 else window.winfo_reqwidth()
        height=window.winfo_height() if window.winfo_height()>1 else window.winfo_reqheight()
        x=max(0,(window.winfo_screenwidth()-width)//2)
        y=max(0,(window.winfo_screenheight()-height)//2)
        window.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError:
        pass

def activate_modal(window: tk.Toplevel, parent=None):
    """Center, bring forward, keep modal, and allow Escape to close."""
    try:
        if parent is not None and parent.winfo_exists(): window.transient(parent)
        center_window(window,parent)
        window.attributes("-topmost",True); window.lift(); window.focus_force(); window.grab_set()
        window.bind("<Escape>",lambda _event:window.destroy(),add="+")
        window.after(450,lambda:window.attributes("-topmost",False) if window.winfo_exists() else None)
    except tk.TclError:
        pass
