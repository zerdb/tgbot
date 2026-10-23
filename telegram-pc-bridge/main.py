import tkinter as tk


def center(window, width, height):
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


if __name__ == "__main__":
    # Import CustomTkinter first so the application has exactly one Tk root.
    # The splash is a Toplevel owned by that root; this keeps CTk StringVar
    # values (token, user id, status) in the same Tcl interpreter.
    import customtkinter as ctk

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#F3F6FB")
    center(splash, 430, 245)

    card = tk.Frame(
        splash,
        bg="#FFFFFF",
        highlightbackground="#DCE6F2",
        highlightthickness=1,
    )
    card.pack(fill="both", expand=True, padx=1, pady=1)

    tk.Label(
        card, text="➤", bg="#FFFFFF", fg="#2583EB",
        font=("Segoe UI", 34, "bold"),
    ).pack(pady=(35, 5))
    tk.Label(
        card, text="Telegram PC Bridge", bg="#FFFFFF", fg="#172033",
        font=("Segoe UI", 19, "bold"),
    ).pack()
    tk.Label(
        card, text="Добро пожаловать", bg="#FFFFFF", fg="#64748B",
        font=("Segoe UI", 10),
    ).pack(pady=(4, 22))

    status = tk.Label(
        card, text="Загрузка интерфейса…", bg="#FFFFFF", fg="#64748B",
        font=("Segoe UI", 9),
    )
    status.pack()

    progress_bg = tk.Frame(card, bg="#E5EDF7", width=290, height=4)
    progress_bg.pack(pady=(10, 0))
    progress_bg.pack_propagate(False)
    progress = tk.Frame(progress_bg, bg="#2583EB", width=70, height=4)
    progress.place(x=0, y=0)

    splash.update_idletasks()
    splash.update()

    status.configure(text="Подготовка Telegram PC Bridge…")
    progress.place_configure(width=190)
    splash.update()

    from app import TelegramBridgeApp

    app = TelegramBridgeApp(root)
    root.update_idletasks()

    status.configure(text="Готово")
    progress.place_configure(width=290)
    splash.update()

    splash.destroy()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()
