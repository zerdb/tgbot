"""Tkinter entry point for installed modular skills."""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from skills_runtime.registry import SkillRegistry
from skills_runtime.workflows import create_sales_summary

class SkillsWindow:
    def __init__(self, parent: tk.Tk, registry: SkillRegistry):
        self.registry = registry
        self.window = tk.Toplevel(parent)
        self.window.title("Навыки голосового помощника")
        self.window.geometry("720x590")
        self.window.minsize(620, 500)
        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.sheet_var = tk.StringVar()
        self.group_var = tk.StringVar()
        self.sum_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Готов к работе")
        self._build()
        self.window.transient(parent)
        self.window.grab_set()

    def _build(self):
        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Установленные навыки", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        panel = ttk.LabelFrame(outer, text="Навыки и их роли", padding=8)
        panel.pack(fill="x", pady=(8, 12))
        roles = {
            "files": "Находит исходный файл.",
            "excel_reader": "Читает книгу и извлекает строки без изменения источника.",
            "calculations": "Считает суммы по явно выбранным столбцам.",
            "excel_writer": "Создаёт отдельный XLSX-отчёт и не перезаписывает файлы.",
        }
        for item in self.registry.describe():
            ttk.Label(panel, text=f"• {item['name']} — {roles.get(item['name'], item['description'])}",
                      wraplength=660).pack(anchor="w", pady=2)
        ttk.Label(outer, text="Сценарий: сводный Excel-отчёт",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
        form = ttk.Frame(outer); form.pack(fill="x")
        fields = [
            ("Исходная книга (.xlsx/.xlsm):", self.source_var),
            ("Лист (необязательно):", self.sheet_var),
            ("Группировать по столбцу:", self.group_var),
            ("Суммировать столбец:", self.sum_var),
            ("Сохранить отчёт как:", self.destination_var),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8)
            if row in (0, 4):
                ttk.Button(form, text="Обзор…",
                           command=self._browse_source if row == 0 else self._browse_destination
                           ).grid(row=row, column=2)
        form.columnconfigure(1, weight=1)
        ttk.Label(outer, text="Укажи точные названия столбцов из первой строки таблицы. "
                  "Исходная книга не меняется; существующий файл отчёта не будет перезаписан.",
                  wraplength=670, justify="left").pack(anchor="w", pady=(12, 8))
        self.run_button = ttk.Button(outer, text="Создать отчёт", command=self._run)
        self.run_button.pack(anchor="w")
        ttk.Label(outer, textvariable=self.status_var, wraplength=670).pack(anchor="w", pady=(10, 0))

    def _browse_source(self):
        path = filedialog.askopenfilename(parent=self.window, title="Выберите Excel-книгу",
                 filetypes=[("Excel", "*.xlsx *.xlsm")])
        if path:
            self.source_var.set(path)
            if not self.destination_var.get().strip():
                p = Path(path)
                self.destination_var.set(str(p.with_name(p.stem + "_сводка.xlsx")))

    def _browse_destination(self):
        path = filedialog.asksaveasfilename(parent=self.window, title="Куда сохранить отчёт",
                 defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if path: self.destination_var.set(path)

    def _run(self):
        source, destination = self.source_var.get().strip(), self.destination_var.get().strip()
        group, total = self.group_var.get().strip(), self.sum_var.get().strip()
        sheet = self.sheet_var.get().strip() or None
        if not all((source, destination, group, total)):
            messagebox.showwarning("Не хватает данных", "Укажи исходный файл, путь отчёта и оба столбца.", parent=self.window)
            return
        self.run_button.configure(state="disabled")
        self.status_var.set("Работа навыков: поиск → чтение → расчёт → запись…")
        def worker():
            try:
                result = create_sales_summary(self.registry, source, destination, group, total, sheet)
                self.window.after(0, lambda: self._finished(result, None))
            except Exception as exc:
                error = str(exc)
                self.window.after(0, lambda: self._finished(None, error))
        threading.Thread(target=worker, daemon=True, name="skills-excel-report").start()

    def _finished(self, result, error):
        self.run_button.configure(state="normal")
        if error:
            self.status_var.set("Не удалось создать отчёт.")
            messagebox.showerror("Ошибка навыка", error, parent=self.window)
            return
        self.status_var.set(f"Готово. Строк: {result['rows_read']}; групп: {result['groups']}; сумма: {result['grand_total']}.")
        messagebox.showinfo("Отчёт создан", f"Файл сохранён:\n{result['report']}", parent=self.window)

def open_skills_window(parent: tk.Tk, registry: SkillRegistry):
    SkillsWindow(parent, registry)
