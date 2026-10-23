import tkinter as tk


def show_splash():
    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.configure(bg="#F3F6FB")

    width, height = 430, 245
    screen_w = splash.winfo_screenwidth()
    screen_h = splash.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")

    card = tk.Frame(
        splash,
        bg="#FFFFFF",
        highlightbackground="#DCE6F2",
        highlightthickness=1,
    )
    card.pack(fill="both", expand=True, padx=1, pady=1)

    tk.Label(
        card,
        text="➤",
        bg="#FFFFFF",
        fg="#2583EB",
        font=("Segoe UI", 34, "bold"),
    ).pack(pady=(35, 5))
    tk.Label(
        card,
        text="Telegram PC Bridge",
        bg="#FFFFFF",
        fg="#172033",
        font=("Segoe UI", 19, "bold"),
    ).pack()
    tk.Label(
        card,
        text="Добро пожаловать",
        bg="#FFFFFF",
        fg="#64748B",
        font=("Segoe UI", 10),
    ).pack(pady=(4, 22))

    status = tk.Label(
        card,
        text="Запуск приложения…",
        bg="#FFFFFF",
        fg="#64748B",
        font=("Segoe UI", 9),
    )
    status.pack()

    progress_bg = tk.Frame(card, bg="#E5EDF7", width=290, height=4)
    progress_bg.pack(pady=(10, 0))
    progress_bg.pack_propagate(False)
    progress = tk.Frame(progress_bg, bg="#2583EB", width=15, height=4)
    progress.place(x=0, y=0)

    splash.update_idletasks()
    return splash, status, progress, progress_bg


if __name__ == "__main__":
    # Native Tk splash appears before importing CustomTkinter and the rest of Bridge.
    splash, splash_status, splash_progress, splash_track = show_splash()
    splash.update()

    splash_status.configure(text="Загрузка интерфейса…")
    splash_progress.place_configure(width=95)
    splash.update()

    import customtkinter as ctk

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    splash_status.configure(text="Подготовка Telegram PC Bridge…")
    splash_progress.place_configure(width=205)
    splash.update()

    from app import TelegramBridgeApp

    root = ctk.CTk()
    root.withdraw()
    app = TelegramBridgeApp(root)
    root.update_idletasks()

    splash_status.configure(text="Готово")
    splash_progress.place_configure(width=290)
    splash.update()

    splash.destroy()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()
