"""Маршрутизация распознанных команд к действиям приложения."""
from __future__ import annotations

import re
import threading
from queue import SimpleQueue
from typing import Callable, Any

from windows_actions import (
    lock_computer, reboot_computer, open_downloads, open_recycle_bin,
    open_application, open_settings, empty_recycle_bin, take_screenshot,
    paste_clipboard_to_excel, save_clipboard_as_note,
    paste_clipboard_to_application,
)
from installed_apps import open_installed_application
from notifications import speak_text
from reminders import add_reminder, add_note, complete_item_by_text
from file_search import search_web, search_files, open_folder_by_name


# Короткие подтверждения Дениса после успешного открытия известных приложений.
_APP_OPEN_PHRASES = {
    "notepad": "Блокнот открыт",
    "calculator": "Калькулятор открыт",
    "browser": "Браузер открыт",
    "word": "Word открыт",
    "excel": "Excel открыт",
    "images": "Папка изображений открыта",
}


class CommandHandler:
    """Обрабатывает команды вне GUI-потока и ставит GUI-действия в очередь."""

    def __init__(
        self,
        get_ui: Callable[[], Any],
        get_ui_thread_id: Callable[[], int | None],
        ui_actions: SimpleQueue,
    ) -> None:
        self._get_ui = get_ui
        self._get_ui_thread_id = get_ui_thread_id
        self._ui_actions = ui_actions

    @staticmethod
    def _announce_success(message: str) -> None:
        """Озвучивает короткое подтверждение; сбой TTS не прерывает команду."""
        text = str(message or "").strip()
        if not text:
            return
        try:
            speak_text(text)
        except Exception as exc:
            print(f"[Озвучивание] Не удалось озвучить подтверждение: {exc}", flush=True)

    def handle_command(self, text: str) -> None:
        """Не блокирует Tk event loop при вызове из главного потока."""
        ui = self._get_ui()
        if ui is not None and self._get_ui_thread_id() == threading.get_ident():
            threading.Thread(
                target=self._handle_command_worker,
                args=(text,),
                daemon=True,
                name="command-handler",
            ).start()
            return
        self._handle_command_worker(text)

    def _handle_command_worker(self, text: str) -> None:
        """Классифицирует намерение и передаёт его соответствующему исполнителю."""
        print(f"Распознана команда: {text}")
        ui = self._get_ui()
        if ui is not None:
            self._ui_actions.put(("busy", "Обработка…"))
        try:
            from intent_router import understand_command
            intent = understand_command(text)
        except Exception as exc:
            if ui is not None:
                self._ui_actions.put(("busy", None))
            error_text = str(exc)
            print(f"Не удалось определить команду: {error_text}")
            if "HTTP 402" in error_text:
                print("У Groq закончились доступные стартовые кредиты или выбранная модель требует платных кредитов. Простые команды Zero Control выполняются локально; для ИИ-классификации нужен доступный баланс или резервная модель.")
            elif "ключ Groq" in error_text:
                print("Добавьте API-ключ Groq в настройках Zero Control.")
            else:
                print("Проверьте подключение к интернету и доступность резервной модели Moondream.")
            return

        action = intent.get("action", "unknown")
        args = intent.get("parameters") or {}
        kind = intent.get("kind", "execute")
        confidence = float(intent.get("confidence", 0) or 0)
        target = intent.get("target") or {}
        source = intent.get("source") or {}
        print(
            "[Намерение] тип=%s цель=%s:%s источник=%s способ=%s" % (
                kind,
                target.get("type", ""),
                target.get("name", ""),
                source.get("type", ""),
                intent.get("method", ""),
            ),
            flush=True,
        )

        if kind == "clarify":
            if ui is not None:
                self._ui_actions.put(("busy", None))
                clarification = str(intent.get("clarification") or "Уточни, пожалуйста, что именно нужно сделать.")
                self._ui_actions.put(("show_ai_answer", ("Нужно уточнение", clarification, None)))
            else:
                print(str(intent.get("clarification") or "Нужно уточнить задачу."), flush=True)
            return

        if kind == "respond" and action not in ("ai_chat", "camera_question"):
            question = str(args.get("question") or intent.get("response") or text).strip()
            if ui is not None:
                self._ui_actions.put(("busy", "Жду ответ ИИ…"))
            self._ui_actions.put(("ai_chat", question))
            return

        if action == "unknown" or confidence < 0.55:
            if ui is not None:
                self._ui_actions.put(("busy", None))
            print("Не удалось надёжно определить намерение. Сформулируй цель или уточни место действия.")
            return

        print(f"Понял намерение: {action} (уверенность {confidence:.2f})")
        parent = ui.root if ui is not None else None
        keep_busy = action in (
            "search_files", "open_folder", "ai_chat", "read_unread_mail",
            "inspect_camera_image", "camera_question",
        )
        if ui is not None and not keep_busy:
            self._ui_actions.put(("busy", None))

        if action == "ai_chat":
            question = str(args.get("question") or text).strip()
            if ui is not None:
                self._ui_actions.put(("busy", "Жду ответ ИИ…"))
            self._ui_actions.put(("ai_chat", question))
        elif action in ("add_contact", "open_contacts"):
            print("[GUI] Открываю общую адресную книгу.", flush=True)
            self._ui_actions.put(("add_contact", action == "add_contact"))
        elif action == "email_compose":
            recipient_name = str(args.get("recipient_name") or "").strip()
            print(f"[Почта] Получатель из голосовой команды: {recipient_name or 'не распознан'}", flush=True)
            # Голосовая команда «отправь на почту <человек>» означает отправку
            # текущих скопированных файлов, даже если ASR/семантика не назвали их
            # отдельным словом. Сам буфер читаем позже в GUI-потоке: чтение из
            # рабочего потока часто сталкивается с временной блокировкой clipboard.
            send_to_person = bool(
                recipient_name
                and re.search(r"\b(отправ\w*|перешл\w*|пошл\w*|передай\w*)\b", text or "", re.IGNORECASE)
            )
            attach_files = bool(args.get("attach_copied_files", False) or send_to_person)
            if attach_files and not args.get("attach_copied_files", False):
                print("[Почта] Для отправки адресату автоматически добавлю скопированные файлы.", flush=True)
            self._ui_actions.put(("email_compose", {
                "attach_copied_files": attach_files,
                "attachment_paths": [],
                "recipient_name": recipient_name,
            }))
        elif action == "inspect_camera_image":
            self._ui_actions.put(("inspect_camera_image", None))
        elif action == "camera_question":
            self._ui_actions.put(("camera_question", str(args.get("question") or text).strip()))
        elif action == "open_assistant_settings":
            self._ui_actions.put((action, None))
        elif action == "open_reminders":
            self._ui_actions.put(("open_reminders", None))
        elif action == "open_mail_client":
            self._ui_actions.put(("open_mail_client", None))
        elif action == "read_unread_mail":
            self._ui_actions.put(("confirm_read_mail", None))
        else:
            try:
                self._execute_action(action, args, text, parent, ui)
            except Exception as exc:
                print(f"Не удалось выполнить команду «{action}»: {exc}", flush=True)
                if ui is not None:
                    self._ui_actions.put(("busy", None))

    def _execute_action(
        self,
        action: str,
        args: dict,
        text: str,
        parent: Any,
        ui: Any,
    ) -> None:
        """Выполняет действие и при успехе коротко озвучивает результат."""
        if action == "save_note":
            save_clipboard_as_note()
        elif action == "clipboard_to_excel":
            # Функция сама сообщает об ошибках пустого/неподходящего буфера.
            paste_clipboard_to_excel()
        elif action == "lock_computer":
            lock_computer()
            self._announce_success("Компьютер заблокирован")
        elif action == "reboot_computer":
            # При отмене пользователем функция просто возвращается.
            reboot_computer()
        elif action == "open_downloads":
            open_downloads()
            self._announce_success("Загрузки открыты")
        elif action == "open_recycle_bin":
            open_recycle_bin()
            self._announce_success("Корзина открыта")
        elif action == "open_application":
            app = str(args.get("app") or "").strip().casefold()
            open_application(app)
            self._announce_success(_APP_OPEN_PHRASES.get(app, "Приложение открыто"))
        elif action == "open_installed_application":
            display_name = open_installed_application(str(args.get("app_name") or ""))
            self._announce_success(f"{display_name} открыт")
        elif action == "open_settings":
            open_settings()
            self._announce_success("Параметры открыты")
        elif action == "empty_recycle_bin":
            # При отмене подтверждения озвучка не нужна.
            empty_recycle_bin()
        elif action == "screenshot":
            take_screenshot()
            self._announce_success("Скриншот сохранён")
        elif action == "inspect_screen":
            self._ui_actions.put(("inspect_screen", None))
        elif action == "paste_clipboard_to_application":
            paste_clipboard_to_application(str(args.get("app_name") or ""))
            self._announce_success("Текст вставлен")
        elif action == "reminder":
            if add_reminder(str(args.get("reminder_text") or text)):
                self._announce_success("Напоминание добавлено")
        elif action == "add_note":
            # add_note уже озвучивает «Запись сохранена.»
            add_note(str(args.get("note_text") or text))
        elif action == "complete_item":
            # complete_item_by_text уже озвучивает «Отмечено выполненным.»
            if not complete_item_by_text(str(args.get("item_text") or "")):
                print("Не нашёл подходящую активную запись. Открой заметки и дела, чтобы выбрать её.")
        elif action == "organize_folder":
            self._ui_actions.put(("organize_folder", None))
        elif action == "search_web":
            search_web(str(args.get("query") or text))
        elif action == "open_folder":
            if ui is not None:
                self._ui_actions.put(("busy", "Ищу папку…"))
            opened = open_folder_by_name(str(args.get("folder") or text), parent)
            if ui is not None:
                self._ui_actions.put(("busy", None))
            if opened:
                self._announce_success("Папка открыта")
        elif action == "search_files":
            if ui is not None:
                self._ui_actions.put(("busy", "Ищу файлы…"))
            search_files(
                str(args.get("query") or text),
                parent,
                export_format=args.get("export_format"),
            )
        else:
            print("Эта операция пока не подключена.")
