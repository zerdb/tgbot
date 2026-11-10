"""Фоновые задачи Zero Control.

Функции выполняются в рабочих потоках и передают результаты в очередь GUI.
"""
from __future__ import annotations

from queue import SimpleQueue
from typing import Any

from ai_chat import ask_ai


def ask_ai_worker(question: str, ui_actions: SimpleQueue) -> None:
    try:
        answer = ask_ai(question)
        result = (question, answer, None)
    except Exception as exc:
        result = (question, None, str(exc))
    ui_actions.put(("ai_chat_result", result))


def camera_inspection_worker(ui_actions: SimpleQueue) -> None:
    try:
        from camera_inspector import inspect_camera
        from notifications import speak_text as speak

        present = inspect_camera()
        if present:
            speak("Начальник есть")
            result = ("Начальник есть", None)
        else:
            speak("Начальника нет")
            result = ("Начальника нет", None)
    except Exception as exc:
        result = ("", str(exc))
    ui_actions.put(("camera_inspection_result", result))


def camera_question_worker(question: str, ui_actions: SimpleQueue) -> None:
    try:
        from camera_inspector import inspect_camera_question
        from notifications import speak_text as speak

        answer = inspect_camera_question(question)
        speak(answer)
        result = (question, answer, None)
    except Exception as exc:
        result = (question, None, str(exc))
    ui_actions.put(("camera_question_result", result))


def mail_reader_worker(ui_actions: SimpleQueue) -> None:
    try:
        from mail_reader import summarize_unread

        answer = summarize_unread()
        result = ("Сводка непрочитанных писем", answer, None)
    except Exception as exc:
        result = ("Сводка непрочитанных писем", None, str(exc))
    ui_actions.put(("ai_chat_result", result))



def office_command_worker(command: str, ui_actions: SimpleQueue) -> None:
    """Run an Office automation command outside the Tkinter thread."""
    try:
        from office_assistant import execute_office_command
        answer = execute_office_command(command)
        result = (command, answer, None)
    except Exception as exc:
        result = (command, None, str(exc))
    ui_actions.put(("office_command_result", result))
