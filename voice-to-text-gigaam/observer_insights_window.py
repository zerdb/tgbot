"""Local pattern insights and user feedback UI."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def open_observer_insights(parent, manager):
    window = tk.Toplevel(parent)
    window.title("GigaAM — Анализ привычек")
    window.geometry("780x540")
    window.minsize(620, 400)
    window.transient(parent)

    status = tk.StringVar(value="Анализ выполняется только локально по метаданным истории.")
    items = ttk.Treeview(window, columns=("title", "status", "date"), show="headings", height=12)
    items.heading("title", text="Наблюдение / предложение")
    items.heading("status", text="Статус")
    items.heading("date", text="Дата")
    items.column("title", width=500)
    items.column("status", width=100)
    items.column("date", width=140)
    items.pack(fill="both", expand=True, padx=12, pady=10)

    description = tk.Text(window, height=5, wrap="word", state="disabled")
    description.pack(fill="x", padx=12, pady=(0, 8))

    def show_description(_event=None):
        selection = items.selection()
        if not selection:
            return
        row = next((x for x in manager.store.list_suggestions(limit=500) if str(x["id"]) == selection[0]), None)
        description.configure(state="normal")
        description.delete("1.0", "end")
        if row:
            description.insert("1.0", row["description"])
        description.configure(state="disabled")

    items.bind("<<TreeviewSelect>>", show_description)

    def refresh():
        for iid in items.get_children():
            items.delete(iid)
        rows = manager.store.list_suggestions(limit=500)
        labels = {"pending": "Новое", "accepted": "Принято", "dismissed": "Отклонено"}
        for row in rows:
            items.insert("", "end", iid=str(row["id"]), values=(
                row["title"], labels.get(row["status"], row["status"]), row["created_at"][:16].replace("T", " ")
            ))
        status.set(f"Предложений: {len(rows)}. Новые: {sum(x['status'] == 'pending' for x in rows)}")

    def analyze():
        try:
            created = manager.analyze_now(days=7)
            refresh()
            messagebox.showinfo("Анализ завершён", f"Новых предложений: {created}\nПроверен период: 7 дней.", parent=window)
        except Exception as exc:
            messagebox.showerror("Ошибка анализа", str(exc), parent=window)

    def decide(value):
        selection = items.selection()
        if not selection:
            messagebox.showwarning("Выберите предложение", "Сначала выберите строку.", parent=window)
            return
        manager.store.update_suggestion(int(selection[0]), value)
        refresh()

    top = ttk.Frame(window, padding=(12, 8, 12, 0))
    top.pack(fill="x")
    ttk.Button(top, text="Проанализировать последние 7 дней", command=analyze).pack(side="left")
    ttk.Button(top, text="Обновить", command=refresh).pack(side="left", padx=8)
    ttk.Button(top, text="Принять", command=lambda: decide("accepted")).pack(side="right")
    ttk.Button(top, text="Неактуально", command=lambda: decide("dismissed")).pack(side="right", padx=8)
    ttk.Label(window, textvariable=status, padding=(12, 0, 12, 8)).pack(anchor="w")
    ttk.Label(window, text="Предложения — гипотезы по повторяющимся метаданным, а не выводы о содержимом ваших файлов.",
              padding=(12, 0, 12, 10), wraplength=740).pack(anchor="w")
    refresh()
    window.grab_set()
    window.wait_window()
