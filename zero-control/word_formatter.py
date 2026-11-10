"""Safe AI-assisted paragraph formatting for the current Microsoft Word selection.

The model only proposes paragraph-level values. Word applies those values directly;
the document text and character-level formatting are never rewritten.
"""
from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import messagebox

from groq_client import chat


_ALLOWED_ALIGNMENTS = {"left", "center", "right", "justify"}
_NUMERIC_LIMITS = {
    "left_indent_pt": (-36.0, 144.0),
    "right_indent_pt": (-36.0, 144.0),
    "first_line_indent_pt": (-36.0, 144.0),
    "space_before_pt": (0.0, 48.0),
    "space_after_pt": (0.0, 48.0),
}
_WORD_ALIGNMENTS = {"left": 0, "center": 1, "right": 2, "justify": 3}


def validate_format_suggestion(payload: dict) -> dict:
    """Keep only supported, bounded paragraph properties from an AI response."""
    if not isinstance(payload, dict):
        raise ValueError("ИИ вернул ответ неверного формата.")

    result = {}
    alignment = payload.get("alignment")
    if alignment is not None:
        normalized = str(alignment).strip().lower()
        if normalized not in _ALLOWED_ALIGNMENTS:
            raise ValueError("ИИ предложил неподдерживаемый тип выравнивания.")
        result["alignment"] = normalized

    for key, (minimum, maximum) in _NUMERIC_LIMITS.items():
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            raise ValueError("ИИ вернул некорректное значение форматирования.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("ИИ вернул некорректное значение форматирования.") from exc
        if not minimum <= number <= maximum:
            raise ValueError("Предложенные ИИ параметры выходят за безопасные пределы.")
        result[key] = number

    if not result:
        raise ValueError("ИИ не предложил параметров форматирования.")
    return result


def _word_selection_snapshot():
    """Read the active Word selection without changing the document."""
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "Для работы с Word установи зависимости Zero Control (pywin32)."
        ) from exc

    pythoncom.CoInitialize()
    try:
        try:
            app = win32com.client.GetActiveObject("Word.Application")
        except Exception as exc:
            raise RuntimeError(
                "Не удалось подключиться к открытому Microsoft Word. "
                "Открой документ и выдели нужный фрагмент."
            ) from exc
        selection = app.Selection
        word_range = selection.Range
        if word_range.Start == word_range.End:
            raise RuntimeError("Сначала выдели фрагмент текста в Word.")
        document_identity = str(app.ActiveDocument.FullName or app.ActiveDocument.Name)
        selected_text = str(word_range.Text or "")
        if not selected_text.strip():
            raise RuntimeError("В выделенном фрагменте нет текста.")
        if len(selected_text) > 12000:
            raise RuntimeError(
                "Выделенный фрагмент слишком большой. Выдели меньшую часть (до 12 000 символов)."
            )

        profiles = []
        paragraphs = word_range.Paragraphs
        for index in range(1, paragraphs.Count + 1):
            paragraph = paragraphs.Item(index)
            try:
                is_list = int(paragraph.Range.ListFormat.ListType) != 0
            except Exception:
                is_list = True
            try:
                style_name = str(paragraph.Range.Style.NameLocal or "")
            except Exception:
                style_name = ""
            if is_list or any(
                token in style_name.lower()
                for token in ("heading", "заголовок", "title", "название")
            ):
                continue
            fmt = paragraph.Format
            profiles.append({
                "paragraph": index,
                "style": style_name[:80],
                "alignment": int(fmt.Alignment),
                "left_indent_pt": round(float(fmt.LeftIndent), 2),
                "right_indent_pt": round(float(fmt.RightIndent), 2),
                "first_line_indent_pt": round(float(fmt.FirstLineIndent), 2),
                "space_before_pt": round(float(fmt.SpaceBefore), 2),
                "space_after_pt": round(float(fmt.SpaceAfter), 2),
            })
        if not profiles:
            raise RuntimeError("В выделении нет обычных абзацев для форматирования.")
        return (
            int(word_range.Start), int(word_range.End), document_identity,
            selected_text, profiles,
        )
    finally:
        pythoncom.CoUninitialize()


def _apply_to_word(start: int, end: int, document_identity: str, expected_text: str, suggestion: dict) -> int:
    """Apply only paragraph properties; never assign or replace Range.Text."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("Word.Application")
        document = app.ActiveDocument
        current_identity = str(document.FullName or document.Name)
        if current_identity != document_identity:
            raise RuntimeError("В Word открыт другой документ. Ничего не применено.")
        word_range = document.Range(start, end)
        if str(word_range.Text or "") != expected_text:
            raise RuntimeError(
                "Выделенный текст изменился после анализа. Ничего не применено — "
                "повтори операцию для актуального выделения."
            )

        paragraphs = word_range.Paragraphs
        applied = 0
        undo_record = getattr(app, "UndoRecord", None)
        record_started = False
        try:
            if undo_record is not None:
                undo_record.StartCustomRecord("Zero Control — форматирование Word")
                record_started = True
            for index in range(1, paragraphs.Count + 1):
                paragraph = paragraphs.Item(index)
                try:
                    if int(paragraph.Range.ListFormat.ListType) != 0:
                        continue
                except Exception:
                    # If Word cannot identify list metadata, do not risk changing
                    # indentation on a potentially structured paragraph.
                    continue
                try:
                    style_name = str(paragraph.Range.Style.NameLocal or "").lower()
                except Exception:
                    style_name = ""
                if any(token in style_name for token in ("heading", "заголовок", "title", "название")):
                    continue

                fmt = paragraph.Format
                if "alignment" in suggestion:
                    fmt.Alignment = _WORD_ALIGNMENTS[suggestion["alignment"]]
                if "left_indent_pt" in suggestion:
                    fmt.LeftIndent = suggestion["left_indent_pt"]
                if "right_indent_pt" in suggestion:
                    fmt.RightIndent = suggestion["right_indent_pt"]
                if "first_line_indent_pt" in suggestion:
                    fmt.FirstLineIndent = suggestion["first_line_indent_pt"]
                if "space_before_pt" in suggestion:
                    fmt.SpaceBefore = suggestion["space_before_pt"]
                if "space_after_pt" in suggestion:
                    fmt.SpaceAfter = suggestion["space_after_pt"]
                applied += 1
        finally:
            if record_started:
                undo_record.EndCustomRecord()
        return applied
    finally:
        pythoncom.CoUninitialize()


def _format_summary(suggestion: dict) -> str:
    labels = {
        "alignment": "Выравнивание",
        "left_indent_pt": "Отступ слева",
        "right_indent_pt": "Отступ справа",
        "first_line_indent_pt": "Отступ первой строки",
        "space_before_pt": "Интервал перед абзацем",
        "space_after_pt": "Интервал после абзаца",
    }
    values = {
        "left": "по левому краю",
        "center": "по центру",
        "right": "по правому краю",
        "justify": "по ширине",
    }
    lines = []
    for key, value in suggestion.items():
        shown = values.get(value, f"{value:g} пт" if isinstance(value, float) else str(value))
        lines.append(f"• {labels[key]}: {shown}")
    return "\n".join(lines)


def open_word_formatter(parent):
    """Ask consent, analyze selection in background, preview, then apply on approval."""
    try:
        start, end, document_identity, selected_text, profiles = _word_selection_snapshot()
    except Exception as exc:
        messagebox.showerror("ИИ — подровнять Word", str(exc), parent=parent)
        return

    approved = messagebox.askyesno(
        "Передать выделенный текст ИИ?",
        "Для анализа выделенный фрагмент будет отправлен подключённой модели Groq. "
        "Документ не будет изменён до твоего подтверждения. Продолжить?",
        parent=parent,
    )
    if not approved:
        return

    progress = tk.Toplevel(parent)
    progress.title("ИИ — подровнять Word")
    progress.resizable(False, False)
    tk.Label(
        progress,
        text="ИИ анализирует структуру выделенных абзацев…",
        padx=24, pady=18, font=("Segoe UI", 10),
    ).pack()
    progress.transient(parent)
    progress.grab_set()

    def analyze():
        try:
            answer = chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Ты анализируешь фрагмент документа Word и предлагаешь "
                            "только безопасные параметры оформления абзацев. "
                            "Не переписывай текст и не меняй смысл. Верни только JSON-объект "
                            "с полями: alignment (left/center/right/justify), "
                            "left_indent_pt, right_indent_pt, first_line_indent_pt, "
                            "space_before_pt, space_after_pt. Числа — в пунктах. "
                            "Учитывай, что выделение может содержать несколько обычных абзацев. "
                            "Не предлагай экстремальные отступы или интервалы. "
                            "Не включай поля, которые не требуется менять."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Предложи единообразное и аккуратное форматирование "
                            "для выделенного фрагмента. Текст:\n" + selected_text
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            suggestion = validate_format_suggestion(json.loads(answer))
            result = (suggestion, None)
        except Exception as exc:
            result = (None, str(exc))

        def finish():
            try:
                progress.destroy()
            except tk.TclError:
                pass
            suggestion, error = result
            if error:
                messagebox.showerror("ИИ — подровнять Word", error, parent=parent)
                return
            preview = (
                "ИИ предлагает изменить параметры абзацев:\n\n"
                + _format_summary(suggestion)
                + "\n\nЖирный шрифт, курсив, подчёркивания и сам текст "
                "не переписываются. Заголовки и маркированные/нумерованные "
                "списки пропускаются. Применить?"
            )
            if not messagebox.askyesno("Предварительный просмотр", preview, parent=parent):
                return
            try:
                count = _apply_to_word(start, end, document_identity, selected_text, suggestion)
            except Exception as exc:
                messagebox.showerror("ИИ — подровнять Word", str(exc), parent=parent)
                return
            if count == 0:
                messagebox.showwarning(
                    "ИИ — подровнять Word",
                    "Не найдено обычных абзацев для изменения. Заголовки и списки не затронуты.",
                    parent=parent,
                )
            else:
                messagebox.showinfo(
                    "Готово",
                    f"Форматирование применено к абзацам: {count}. "
                    "Изменения можно отменить в Word сочетанием Ctrl+Z. Документ не сохранён автоматически.",
                    parent=parent,
                )

        try:
            parent.after(0, finish)
        except tk.TclError:
            pass

    threading.Thread(target=analyze, daemon=True, name="word-format-ai").start()
