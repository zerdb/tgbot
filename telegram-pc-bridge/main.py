import customtkinter as ctk

from app import TelegramBridgeApp


if __name__ == "__main__":
    root = ctk.CTk()
    TelegramBridgeApp(root)
    root.mainloop()
