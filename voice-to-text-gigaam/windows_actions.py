"""Windows-specific actions used by the voice assistant."""
from __future__ import annotations

import csv
import io
import os
import subprocess
import time

import keyboard
import pyperclip
from winotify import Notification
from pathlib import Path
from datetime import datetime
from PIL import ImageGrab
from openpyxl import Workbook
from notifications import speak_text
from reminders import add_note

SCREENSHOT_DIR = Path(__file__).resolve().parent / "Скриншоты"
CLIPBOARD_TABLES_DIR = Path(__file__).resolve().parent / "Таблицы"


def windows_only():
    if os.name != "nt":
        raise OSError("Эта команда поддерживается только в Windows.")


def confirm_action(title: str, message: str) -> bool:
    windows_only()
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, message, title, 0x4 | 0x20) == 6


def lock_computer():
    windows_only()
    import ctypes
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("Windows не смогла заблокировать рабочую станцию.")
    print("Компьютер заблокирован.")


def reboot_computer():
    if not confirm_action("Подтверждение перезагрузки", "Перезагрузить компьютер сейчас? Сохраните открытые документы."):
        print("Перезагрузка отменена.")
        return
    subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _bring_window_to_front(title_parts: tuple[str, ...], timeout: float = 3.0):
    """Restore and foreground an already-open Windows window by its title."""
    import ctypes
    import time

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    target = None
    deadline = time.monotonic() + timeout

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_callback(hwnd, _):
        nonlocal target
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.casefold()
        if any(part.casefold() in title for part in title_parts):
            target = hwnd
            return False
        return True

    while time.monotonic() < deadline:
        target = None
        user32.EnumWindows(enum_callback, 0)
        if target:
            user32.ShowWindow(target, 9)
            user32.BringWindowToTop(target)
            foreground = user32.GetForegroundWindow()
            current_thread = kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(target, None)
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
            attached_target = False
            attached_foreground = False
            try:
                if target_thread and target_thread != current_thread:
                    attached_target = bool(user32.AttachThreadInput(current_thread, target_thread, True))
                if foreground_thread and foreground_thread != current_thread:
                    attached_foreground = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
                user32.SetForegroundWindow(target)
                user32.SetActiveWindow(target)
                user32.SetFocus(target)
            finally:
                if attached_foreground:
                    user32.AttachThreadInput(current_thread, foreground_thread, False)
                if attached_target:
                    user32.AttachThreadInput(current_thread, target_thread, False)
            return
        time.sleep(0.15)


def open_downloads():
    windows_only()
    path = Path.home() / "Downloads"
    if not path.exists():
        path = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Загрузки"
    os.startfile(str(path))
    _bring_window_to_front(("Загрузки", "Downloads"))


def open_recycle_bin():
    """Open the Recycle Bin without deleting anything."""
    windows_only()
    subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"])


def open_application(app_name: str):
    """Open a known Windows application using a strict allowlist."""
    windows_only()
    apps = {
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "word": ["cmd", "/c", "start", "", "winword"],
        "excel": ["cmd", "/c", "start", "", "excel"],
        "images": ["explorer.exe", "shell:MyPictures"],
    }
    if app_name == "browser":
        import webbrowser
        webbrowser.open("https://www.google.com")
    elif app_name in apps:
        subprocess.Popen(apps[app_name])
    else:
        raise ValueError("Неизвестное приложение.")


def open_settings():
    windows_only()
    os.startfile("ms-settings:")
    _bring_window_to_front(("Параметры", "Settings"))


def empty_recycle_bin():
    if not confirm_action("Очистка корзины", "Безвозвратно удалить все файлы из корзины? Это действие нельзя отменить."):
        print("Очистка корзины отменена.")
        return
    import ctypes
    result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
    if result:
        raise OSError(f"Не удалось очистить корзину (код {result}).")
    print("Корзина очищена.")


def take_screenshot():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    destination = SCREENSHOT_DIR / f"Screenshot_{stamp}.png"
    counter = 1
    while destination.exists():
        destination = SCREENSHOT_DIR / f"Screenshot_{stamp}_{counter}.png"
        counter += 1
    ImageGrab.grab(all_screens=True).save(destination, "PNG")
    print(f"Скриншот сохранён: {destination}")
    try:
        os.startfile(str(destination))
        print("Открываю скриншот.")
    except OSError as exc:
        print(f"Скриншот сохранён, но не удалось открыть его автоматически: {exc}")


def paste_clipboard_to_excel():
    """Create an XLSX workbook from tab/newline-delimited clipboard data and open it."""
    windows_only()
    content = pyperclip.paste()
    if not isinstance(content, str) or not content.strip():
        print("Буфер обмена пуст. Сначала скопируйте таблицу.")
        return
    if "\t" not in content and "\n" not in content and "\r" not in content:
        print("В буфере нет табуляции или переносов строк. Скопируйте таблицу.")
        return

    try:
        rows = csv.reader(io.StringIO(content, newline=""), delimiter="\t", quotechar='"')
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Данные"

        row_count = 0
        for row_count, row in enumerate(rows, start=1):
            for column, value in enumerate(row, start=1):
                worksheet.cell(row=row_count, column=column, value=value)

        if row_count == 0:
            print("В буфере не удалось найти строки таблицы.")
            return

        for column_cells in worksheet.columns:
            max_length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=0)
            column_letter = column_cells[0].column_letter
            worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 10), 255)

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        CLIPBOARD_TABLES_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        destination = CLIPBOARD_TABLES_DIR / f"Таблица_{stamp}.xlsx"
        counter = 1
        while destination.exists():
            destination = CLIPBOARD_TABLES_DIR / f"Таблица_{stamp}_{counter}.xlsx"
            counter += 1

        workbook.save(destination)
        os.startfile(str(destination))
        print(f"Таблица создана и открыта в Excel: {destination}")
    except Exception as exc:
        print(f"Не удалось создать таблицу Excel: {exc}")
        raise


def save_clipboard_as_note():
    """Save clipboard text as an item in the unified notes and tasks store."""
    windows_only()
    content = pyperclip.paste()
    if not isinstance(content, str) or not content.strip():
        print("Буфер обмена пуст. Сначала скопируйте текст.")
        return
    if add_note(content.strip()):
        print("Текст из буфера добавлен в общие заметки и дела.")
        try:
            Notification(app_id="Zero Control", title="Запись сохранена",
                         msg="Текст добавлен в раздел «Заметки и дела».", duration="short").show()
        except Exception as exc:
            print(f"Не удалось показать всплывающее уведомление: {exc}")


def clean_clipboard_text():
    """Normalize copied web/PDF text while preserving paragraph boundaries."""
    windows_only()
    content = pyperclip.paste()
    if not isinstance(content, str) or not content.strip():
        print("Буфер обмена пуст. Сначала скопируйте текст.")
        return
    cleaned = content.replace("\r\n", "\n").replace("\r", "\n")
    for character in ("\u00a0", "\u202f"):
        cleaned = cleaned.replace(character, " ")
    for character in ("\u00ad", "\u200b", "\u200c", "\u200d", "\ufeff"):
        cleaned = cleaned.replace(character, "")
    cleaned = cleaned.replace("\t", " ")
    import re
    paragraphs = re.split(r"\n\s*\n+", cleaned.strip())
    normalized = []
    for paragraph in paragraphs:
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph)
        paragraph = re.sub(r"[ \f\v]+", " ", paragraph).strip()
        if paragraph:
            normalized.append(paragraph)
    result = "\n\n".join(normalized)
    pyperclip.copy(result)
    print(f"Текст очищен и возвращён в буфер обмена ({len(result)} символов).")
