import customtkinter as ctk

from app import TelegramBridgeApp


if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    # Keep startup reliable: one CTk root, no secondary Tk/Toplevel splash.
    # The heavy Telegram/PC modules are already lazy-loaded by app.py.
    root = ctk.CTk()
    TelegramBridgeApp(root)
    root.mainloop()
