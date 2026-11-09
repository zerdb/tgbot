"""Zero Control — голосовой помощник для Windows."""
from __future__ import annotations

import threading
import queue
import traceback

import tkinter as tk

from keyboard_listener import KeyboardListener
from audio_engine import AudioEngine

# Показываем заставку до импорта модулей приложения.
_splash = tk.Tk()
_splash.overrideredirect(True)
_splash.attributes("-topmost", True)
_splash.attributes("-alpha", 0.96)
_splash.configure(bg="#202124")
_splash_frame = tk.Frame(_splash, bg="#202124", padx=16, pady=10)
_splash_frame.pack()
tk.Label(_splash_frame, text="⏳", font=("Segoe UI Emoji", 22), fg="#fbbc04", bg="#202124").pack(side="left", padx=(0, 9))
tk.Label(_splash_frame, text="Загружается помощник…", font=("Segoe UI", 10, "bold"), fg="white", bg="#202124").pack(side="left")
_splash.update_idletasks()
_splash_width, _splash_height = _splash.winfo_reqwidth(), _splash.winfo_reqheight()
_splash_x = _splash.winfo_screenwidth() - _splash_width - 24
_splash_y = (_splash.winfo_screenheight() - _splash_height) // 2
_splash.geometry(f"+{_splash_x}+{_splash_y}")
_splash.update_idletasks()
_splash.update()

# Импортируем прикладные модули после показа заставки.
from command_handler import CommandHandler
from background_workers import (
    ask_ai_worker,
    camera_inspection_worker,
    camera_question_worker,
    mail_reader_worker,
)

# Все стандартные уведомления приложения озвучиваются голосом Denis.
from notifications import install_messagebox_voice
install_messagebox_voice()

from reminders import start_reminder_service, stop_reminder_service, deliver_due_reminders
from file_search import start_file_search_ui
from folder_organizer import open_folder_organizer
from assistant_window import AssistantWindow, show_ai_answer
from mail_client import open_mail_client
from workspace_window import open_workspace
from reminders_window import open_reminders
from screen_inspector import open_screen_inspector
from camera_window import open_camera_viewer
from notes_window import open_notes_window

_ui = None  # GUI создаётся позже, после загрузки модулей
_command_handler = None
_audio_engine = None
_keyboard_listener = None


_ui_actions = queue.SimpleQueue()


def update_ui_status(listening=None, recording=None):
    """Queue status changes so Tkinter is only touched by its main thread."""
    if _ui is not None:
        _ui_actions.put(("status", {"listening": listening, "recording": recording}))


def handle_command(text: str):
    """Совместимый callback для GUI; логика находится в CommandHandler."""
    if _command_handler is None:
        print("Обработчик команд ещё не инициализирован.")
        return
    _command_handler.handle_command(text)


def main():
    global _ui, _ui_thread_id, _keyboard_listener, _command_handler, _audio_engine

    # Тяжёлые аудиозависимости загружаются после показа заставки.
    _audio_engine = AudioEngine(
        get_ui=lambda: _ui,
        update_ui_status=update_ui_status,
        handle_command=handle_command,
    )
    _audio_engine.load_dependencies()

    # Загружаем Piper и голос Денис заранее в фоновом потоке.
    # Интерфейс и загрузка GigaAM не ждут завершения этой операции.
    from notifications import initialize_speech_engine
    initialize_speech_engine()

    _ui = AssistantWindow(
        on_close=shutdown,
        on_command=handle_command,
        microphone_status="ПРОВЕРКА",
        on_open_mail=lambda: open_mail_client(_ui.root),
        on_open_files=lambda: open_workspace(_ui.root),
        on_open_reminders=lambda: open_reminders(_ui.root),
        on_open_screen=lambda: open_screen_inspector(_ui.root),
        on_open_other=lambda: open_camera_viewer(_ui.root),
        on_open_notes=lambda: open_notes_window(_ui.root),
        on_open_settings=lambda: _ui_actions.put(("open_assistant_settings", None)),
    )
    _ui_thread_id = threading.get_ident()
    _command_handler = CommandHandler(
        get_ui=lambda: _ui,
        get_ui_thread_id=lambda: _ui_thread_id,
        ui_actions=_ui_actions,
    )
    # Сначала создаём и отображаем главное окно, затем убираем заставку —
    # между ними не должно быть пустой паузы.
    _ui.root.update_idletasks()
    _ui.root.update()
    _splash.destroy()

    microphone_found = _audio_engine.check_microphone()
    _ui.set_status(microphone="НАЙДЕН" if microphone_found else "НЕ НАЙДЕН")
    _audio_engine.configure_ffmpeg()
    _audio_engine.load_model()
    _ui.set_busy_overlay(None)
    _keyboard_listener = KeyboardListener(
        start_recording=_audio_engine.start_recording,
        promote_to_dictation=_audio_engine.promote_to_dictation,
        stop_recording=_audio_engine.stop_recording,
        is_dictation_active=lambda: _audio_engine.is_dictation_active,
    )
    _keyboard_listener.install()
    start_file_search_ui(_ui.root, busy_callback=_ui.set_busy_overlay)

    def check_mft_refresh_reminder():
        try:
            import time
            from agent_core import load_settings, save_settings
            settings = load_settings()
            last_refresh = int(settings.get("mft_last_refresh_at", 0) or 0)
            last_reminder = int(settings.get("mft_last_reminder_at", 0) or 0)
            interval = int(settings.get("mft_refresh_interval_days", 7) or 7)
            now = int(time.time())
            if last_refresh and now - last_refresh >= interval * 86400 and now - last_reminder >= 3 * 86400:
                from notifications import show_notification
                show_notification("Zero Control — индекс файлов", "Пора обновить индекс MFT. Открой настройки и нажми «Обновить индекс сейчас».")
                settings["mft_last_reminder_at"] = now
                save_settings(settings)
        except Exception as exc:
            print(f"[MFT] Не удалось проверить напоминание: {exc}", flush=True)
        finally:
            try:
                _ui.root.after(60 * 60 * 1000, check_mft_refresh_reminder)
            except Exception:
                pass

    _ui.root.after(5000, check_mft_refresh_reminder)
    # Таймер очереди напоминаний обслуживается главным потоком Tkinter.
    start_reminder_service()

    def process_background_events():
        # Сначала гарантируем следующий запуск опроса: ошибка любого обработчика
        # не должна навсегда остановить очередь GUI-действий.
        try:
            _ui.root.after(25, process_background_events)
        except Exception:
            return

        try:
            if _keyboard_listener is not None:
                _keyboard_listener.process_events()
        except Exception:
            print("[GUI] Ошибка обработки клавиатурных событий:", flush=True)
            traceback.print_exc()

        while True:
            try:
                ui_action, value = _ui_actions.get_nowait()
            except queue.Empty:
                break

            print(f"[GUI] Получено действие из очереди: {ui_action}", flush=True)
            try:
                if ui_action == "busy":
                    _ui.set_busy_overlay(value)
                elif ui_action == "status":
                    status = value if isinstance(value, dict) else {}
                    _ui.set_status(listening=status.get("listening"))
                    recording = status.get("recording")
                    if recording is not None:
                        _ui.set_recording_overlay(bool(recording), mode=recording if recording else None)
                elif ui_action == "show_ai_answer":
                    question, answer, error = value
                    show_ai_answer(_ui.root, question, answer, error)
                elif ui_action == "organize_folder":
                    open_folder_organizer(_ui.root)
                elif ui_action == "add_contact":
                    print("[GUI] Открываю раздел контактов почтового клиента.", flush=True)
                    open_mail_client(_ui.root, initial_tab="contacts", start_new_contact=bool(value))
                elif ui_action == "email_compose":
                    print("[GUI] Открываю редактор письма в почтовом клиенте.", flush=True)
                    options = value if isinstance(value, dict) else {}
                    open_mail_client(
                        _ui.root,
                        initial_tab="compose",
                        add_files_on_open=bool(options.get("attach_copied_files", False)),
                        recipient_name=str(options.get("recipient_name") or ""),
                        initial_attachment_paths=options.get("attachment_paths") or [],
                    )
                elif ui_action == "inspect_screen":
                    print("[Экран] Делаю снимок монитора и открываю изображение.", flush=True)
                    from screen_inspector import show_screen_snapshot
                    show_screen_snapshot(_ui.root)
                elif ui_action == "camera_question":
                    _ui.set_busy_overlay("Получаю кадр и анализирую вопрос…")
                    threading.Thread(target=camera_question_worker, args=(str(value or ""), _ui_actions), daemon=True, name="camera-question").start()
                elif ui_action == "camera_question_result":
                    _ui.set_busy_overlay(None)
                    question, answer, error = value
                    if error:
                        print("[Камера] " + error, flush=True)
                    else:
                        print("[Камера] " + answer, flush=True)
                        show_ai_answer(_ui.root, question, answer, None)
                elif ui_action == "inspect_camera_image":
                    _ui.set_busy_overlay("Получаю кадр и проверяю его через ИИ…")
                    threading.Thread(target=camera_inspection_worker, args=(_ui_actions,), daemon=True, name="camera-inspection").start()
                elif ui_action == "camera_inspection_result":
                    _ui.set_busy_overlay(None)
                    result_text, error = value
                    print("[Камера] " + (error if error else result_text), flush=True)
                elif ui_action == "open_assistant_settings":
                    from settings_window import open_settings_window
                    open_settings_window(_ui.root)
                elif ui_action == "open_reminders":
                    open_reminders(_ui.root)
                elif ui_action == "open_mail_client":
                    open_mail_client(_ui.root)
                elif ui_action == "confirm_read_mail":
                    from tkinter import messagebox
                    approved = messagebox.askyesno(
                        "Прочитать новые письма",
                        "Для составления сводки текст непрочитанных писем будет передан подключённой модели Groq. Продолжить?",
                        parent=_ui.root,
                    )
                    if approved:
                        _ui.set_busy_overlay("Проверяю входящую почту…")
                        threading.Thread(target=mail_reader_worker, args=(_ui_actions,), daemon=True, name="mail-reader").start()
                    else:
                        _ui.set_busy_overlay(None)
                elif ui_action == "ai_chat":
                    question = str(value or "").strip()
                    if question:
                        print("[ИИ] Отправляю вопрос подключённой модели.", flush=True)
                        _ui.set_busy_overlay("Жду ответ ИИ…")
                        threading.Thread(target=ask_ai_worker, args=(question, _ui_actions), daemon=True).start()
                elif ui_action == "ai_chat_result":
                    question, answer, error = value
                    _ui.set_busy_overlay(None)
                    show_ai_answer(_ui.root, question, answer, error)
                else:
                    print(f"[GUI] Неизвестное действие: {ui_action}", flush=True)
            except Exception:
                print(f"[GUI] Не удалось выполнить действие {ui_action}:", flush=True)
                traceback.print_exc()

        try:
            deliver_due_reminders()
        except Exception:
            print("[GUI] Ошибка доставки напоминаний:", flush=True)
            traceback.print_exc()

    _ui.root.after(25, process_background_events)
    _ui.run()


def shutdown():
    stop_reminder_service()
    if _audio_engine is not None and _audio_engine.is_recording:
        _audio_engine.stop_recording()
    if _keyboard_listener is not None:
        _keyboard_listener.remove()
    print("Работа программы завершена.")

if __name__ == "__main__":
    main()
