import customtkinter as ctk

from app import TelegramBridgeApp


if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    TelegramBridgeApp(root)
    root.mainloop()
