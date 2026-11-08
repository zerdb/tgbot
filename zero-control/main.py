"""Zero Control — голосовой помощник для Windows."""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import queue
import traceback
from pathlib import Path

import tkinter as tk

from keyboard_listener import KeyboardListener
from command_handler import CommandHandler
from background_workers import (
    ask_ai_worker,
    camera_inspection_worker,
    camera_question_worker,
    mail_reader_worker,
)

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


SAMPLE_RATE = 16000
CHANNELS = 1
MAX_CHUNK_SECONDS = 24

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_DIR = Path(os.getenv("ZERO_CONTROL_MODEL_DIR", os.getenv("GIGAAM_MODEL_DIR", str(PROJECT_DIR.parent / "GigaAM-v3")))).expanduser().resolve()
SCREENSHOT_DIR = PROJECT_DIR / "Скриншоты"

_model = None
_stream = None
_audio_chunks: list[np.ndarray] = []
_recording = False
_recording_mode = "text"
_lock = threading.Lock()
_transcription_lock = threading.Lock()
_ui = None
_ui_actions = queue.SimpleQueue()


def update_ui_status(listening=None, recording=None):
    """Queue status changes so Tkinter is only touched by its main thread."""
    if _ui is not None:
        _ui_actions.put(("status", {"listening": listening, "recording": recording}))


def configure_ffmpeg():
    source = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    target_dir = Path(tempfile.gettempdir()) / "zero_control_ffmpeg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "ffmpeg.exe"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    os.environ["PATH"] = str(target_dir) + os.pathsep + os.environ.get("PATH", "")



def check_microphone() -> bool:
    try:
        device = sd.query_devices(kind="input")
        if device["max_input_channels"] < CHANNELS:

            return False
    except (sd.PortAudioError, OSError) as exc:

        return False

    return True


def load_model():
    global _model
    if not (MODEL_DIR / "config.json").is_file():
        raise FileNotFoundError(
            f"Локальная модель GigaAM не найдена: {MODEL_DIR}\n"
            "Поместите модель ai-sage/GigaAM-v3 (revision e2e_rnnt) "
            "в папку GigaAM-v3 рядом с папкой приложения."
        )

    _model = AutoModel.from_pretrained(str(MODEL_DIR), trust_remote_code=True, local_files_only=True)
    _model.eval()



def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Состояние аудиоустройства: {status}")
    with _lock:
        if _recording:
            _audio_chunks.append(indata.copy())


def start_recording(mode: str):
    global _stream, _recording, _recording_mode, _audio_chunks
    with _lock:
        if _recording:
            return
        _audio_chunks = []
        _recording_mode = mode
        _recording = True
    try:
        # Сначала мгновенно показываем уже подготовленную плашку, затем запускаем аудиопоток.
        update_ui_status("ИДЁТ ДИКТОВКА" if mode == "text" else "СЛУШАЮ ГОЛОСОВУЮ КОМАНДУ", recording=mode)
        if _ui is not None:
            _ui.root.update_idletasks()
            _ui.root.update()
        _stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=audio_callback)
        _stream.start()
        key_name = "Right Ctrl+Right Shift" if mode == "text" else "правый Ctrl"
        purpose = "для ввода текста" if mode == "text" else "для голосовой команды"
        print(f"Идёт запись {purpose}. Отпустите {key_name}, чтобы выполнить.")
    except (sd.PortAudioError, OSError) as exc:
        with _lock:
            _recording = False
        _stream = None
        print(f"Не удалось начать запись: {exc}")
        update_ui_status("ОШИБКА ЗАПИСИ", recording=False)


def promote_to_dictation():
    """If Right Shift joins an active Right Ctrl recording, switch to dictation."""
    global _recording_mode
    with _lock:
        if not _recording or _recording_mode == "text":
            return
        _recording_mode = "text"
    print("Режим переключён на диктовку: удерживайте Right Ctrl + Right Shift.")
    update_ui_status("ДИКТОВКА", recording="text")


def stop_recording():
    global _stream, _recording
    with _lock:
        if not _recording:
            return
        _recording = False
        chunks = list(_audio_chunks)
        mode = _recording_mode
    stream, _stream = _stream, None
    if stream is not None:
        try:
            stream.stop()
        finally:
            stream.close()
    update_ui_status("РАСПОЗНАЮ РЕЧЬ", recording=False)
    if not chunks:
        print("Звук не записан: микрофон не передал аудиоданные.")
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
        return
    audio_data = np.concatenate(chunks, axis=0).reshape(-1)
    if audio_data.size == 0:
        print("Звук не записан.")
        return
    print(f"Запись завершена: {len(audio_data) / SAMPLE_RATE:.2f} сек.")
    worker = transcribe_and_paste if mode == "text" else transcribe_and_execute
    threading.Thread(target=worker, args=(audio_data,), daemon=True).start()


def transcribe_audio_file(audio_data: np.ndarray) -> str:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_path = Path(tmp.name)
        sf.write(str(temp_path), audio_data, SAMPLE_RATE, subtype="PCM_16")
        with torch.inference_mode():
            return _model.transcribe(str(temp_path)).strip()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def transcribe_parts(audio_data: np.ndarray, label: str) -> str:
    chunk_size = SAMPLE_RATE * MAX_CHUNK_SECONDS
    parts = [audio_data[i:i + chunk_size] for i in range(0, len(audio_data), chunk_size)]
    results = []
    for index, part in enumerate(parts, start=1):
        if len(parts) > 1:
            print(f"Распознаю {label} {index} из {len(parts)}...")
        result = transcribe_audio_file(part)
        if result:
            results.append(result)
    return " ".join(results).strip()


def transcribe_and_paste(audio_data: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
        return
    try:
        print("Распознаю речь локально...")
        text = transcribe_parts(audio_data, "фрагмент")
        if text:
            try:
                from agent_core import load_settings
                if load_settings().get("clean_dictation_with_ai", False):
                    print("Очищаю текст диктовки с помощью ИИ...")
                    from groq_client import chat
                    cleaned = chat(
                        [
                            {
                                "role": "system",
                                "content": (
                                    "Ты редактор расшифровки русской устной речи. "
                                    "Убери слова-паразиты, случайные повторы, запинки, "
                                    "оговорки и незавершённые дубли фраз. Сохрани исходный "
                                    "смысл, факты, имена, числа и стиль говорящего. "
                                    "Не пересказывай и не сокращай содержательные мысли, "
                                    "не добавляй ничего от себя. Верни только готовый текст "
                                    "без пояснений и кавычек."
                                ),
                            },
                            {"role": "user", "content": text},
                        ],
                        temperature=0.1,
                        max_tokens=max(300, min(2000, len(text) // 2 + 200)),
                        timeout=60,
                    ).strip()
                    if cleaned:
                        text = cleaned
                        print("ИИ-очистка диктовки завершена.")
                    else:
                        print("ИИ вернул пустой текст; использую исходную расшифровку.")
            except Exception as exc:
                print(f"Не удалось очистить диктовку через ИИ; использую исходный текст: {exc}")
            pyperclip.copy(text)
            keyboard.send("ctrl+v")
            print(f"Текст распознан и вставлен: {text}")
        else:
            print("Речь не распознана.")
    except Exception as exc:
        print(f"Ошибка распознавания: {exc}")
        traceback.print_exc()
    finally:
        _transcription_lock.release()
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")


def handle_command(text: str):
    """Совместимый callback для GUI; логика находится в CommandHandler."""
    if _command_handler is None:
        print("Обработчик команд ещё не инициализирован.")
        return
    _command_handler.handle_command(text)


def transcribe_and_execute(audio_data: np.ndarray):
    if not _transcription_lock.acquire(blocking=False):
        print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
        return
    try:
        print("Распознаю голосовую команду...")
        text = transcribe_parts(audio_data, "фрагмент команды")
        if text:
            try:
                handle_command(text)
            except Exception as exc:
                print(f"Ошибка выполнения команды: {exc}")
                traceback.print_exc()
        else:
            print("Голосовая команда не распознана.")
    except Exception as exc:
        print(f"Ошибка распознавания команды: {exc}")
        traceback.print_exc()
    finally:
        _transcription_lock.release()
        update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")


def main():
    global _ui, _ui_thread_id, _keyboard_listener, _command_handler, imageio_ffmpeg, keyboard, np, pyperclip, sd, sf, ImageGrab, audio, torch, AutoModel

    # Заставка уже показана до импорта модулей приложения.
    # Долгая загрузка проходит за заставкой; главное окно пока не открываем.
    import imageio_ffmpeg
    import keyboard
    import numpy as np
    import pyperclip
    import sounddevice as sd
    import soundfile as sf
    from PIL import ImageGrab
    from winotify import audio
    import torch
    from transformers import AutoModel
    from notifications import initialize_speech_engine

    # Загружаем Piper и голос Денис заранее в фоновом потоке.
    # Интерфейс и загрузка GigaAM не ждут завершения этой операции.
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

    microphone_found = check_microphone()
    _ui.set_status(microphone="НАЙДЕН" if microphone_found else "НЕ НАЙДЕН")
    configure_ffmpeg()
    load_model()
    _ui.set_busy_overlay(None)
    _keyboard_listener = KeyboardListener(
        start_recording=start_recording,
        promote_to_dictation=promote_to_dictation,
        stop_recording=stop_recording,
        is_dictation_active=lambda: _recording and _recording_mode == "text",
    )
    _keyboard_listener.install()
    start_file_search_ui(_ui.root, busy_callback=_ui.set_busy_overlay)
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
    with _lock:
        active = _recording
    if active:
        stop_recording()
    if _keyboard_listener is not None:
        _keyboard_listener.remove()
    print("Работа программы завершена.")

if __name__ == "__main__":
    main()
