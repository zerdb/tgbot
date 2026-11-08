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
        style = __import__("tkinter.ttk", fromlist=["Style"]).Style(window)
        style.configure("Primary.TButton", background="#2474D2", foreground="#FFFFFF",
                        bordercolor="#1D63B5", padding=(10, 6),
                        font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton",
                  background=[("active", "#155DB5"), ("pressed", "#124F99")],
                  foreground=[("active", "#FFFFFF")])
        style.configure("Danger.TButton", background="#D94A4A", foreground="#FFFFFF",
                        bordercolor="#BD3838", padding=(10, 6),
                        font=("Segoe UI", 9, "bold"))
        style.map("Danger.TButton",
                  background=[("active", "#BD3838"), ("pressed", "#A92F2F")],
                  foreground=[("active", "#FFFFFF")])

        def color_action_buttons(widget):
            ttk = __import__("tkinter.ttk", fromlist=["Button"])
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    label = str(child.cget("text") or "").strip().lower()
                    if any(word in label for word in ("отмена", "отменить", "выход", "закрыть")):
                        child.configure(style="Danger.TButton")
                    elif any(word in label for word in ("сохранить", "применить", "отправить",
                                                        "добавить", "подтвердить", "готово", "ок")):
                        child.configure(style="Primary.TButton")
                color_action_buttons(child)

        color_action_buttons(window)
        window.after(450,lambda:window.attributes("-topmost",False) if window.winfo_exists() else None)
    except tk.TclError:
        pass


def apply_modern_style(window: tk.Toplevel):
    """Apply the shared compact Zero Control palette to secondary Tk windows."""
    try:
        window.configure(bg="#F4F6FB")
        style = __import__("tkinter.ttk", fromlist=["Style"]).Style(window)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#F4F6FB")
        style.configure("TLabel", background="#F4F6FB", foreground="#172033",
                        font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 6),
                        background="#FFFFFF", foreground="#172033",
                        bordercolor="#E6E9F2")
        style.map("TButton", background=[("active", "#F0EFFF")],
                  foreground=[("active", "#5146D8")])
        style.configure("TEntry", padding=(7, 5), fieldbackground="#FFFFFF",
                        foreground="#172033", bordercolor="#E6E9F2")
        style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF",
                        foreground="#172033", rowheight=27, borderwidth=0,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#EEF0F7",
                        foreground="#172033", font=("Segoe UI", 9, "bold"),
                        padding=(7, 6))
        style.map("Treeview", background=[("selected", "#E8E6FF")],
                  foreground=[("selected", "#172033")])
        style.configure("TScrollbar", troughcolor="#F4F6FB",
                        background="#D9DDE8", borderwidth=0, arrowsize=12)
    except tk.TclError:
        pass
