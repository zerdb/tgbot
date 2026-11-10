"""AI-assisted paragraph and character formatting for the current Word selection.

The model proposes formatting only; document text is never rewritten.
"""
from __future__ import annotations

import json
import re
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
    if "paragraphs" in payload:
        entries = payload.get("paragraphs")
        if not isinstance(entries, list):
            raise ValueError("ИИ вернул некорректный список абзацев.")
        normalized = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("ИИ вернул некорректное описание абзаца.")
            paragraph_number = entry.get("paragraph")
            if isinstance(paragraph_number, bool) or not isinstance(paragraph_number, int) or paragraph_number < 1:
                raise ValueError("ИИ вернул некорректный номер абзаца.")
            if paragraph_number in seen:
                raise ValueError("ИИ повторил номер абзаца в предложении.")
            seen.add(paragraph_number)
            properties = {key: value for key, value in entry.items() if key != "paragraph"}
            if not properties:
                raise ValueError("ИИ не указал параметры для одного из абзацев.")
            normalized.append({"paragraph": paragraph_number, **validate_format_suggestion(properties)})
        if normalized:
            result["paragraphs"] = normalized
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

    if "character_formats" in payload:
        spans = payload.get("character_formats")
        if not isinstance(spans, list):
            raise ValueError("ИИ вернул некорректный список символьного форматирования.")
        normalized_spans = []
        for span in spans:
            if not isinstance(span, dict):
                raise ValueError("ИИ вернул некорректный диапазон символьного форматирования.")
            start, end = span.get("start"), span.get("end")
            if (isinstance(start, bool) or not isinstance(start, int)
                    or isinstance(end, bool) or not isinstance(end, int)
                    or start < 0 or end <= start):
                raise ValueError("ИИ вернул некорректные границы символьного форматирования.")
            item = {"start": start, "end": end}
            for key in ("bold", "italic", "underline"):
                if key in span:
                    if not isinstance(span[key], bool):
                        raise ValueError("ИИ вернул некорректное значение символьного форматирования.")
                    item[key] = span[key]
            if len(item) == 2:
                raise ValueError("ИИ не указал свойства символьного форматирования.")
            normalized_spans.append(item)
        result["character_formats"] = normalized_spans

    if not result:
        raise ValueError("ИИ не предложил параметров форматирования.")
    return result


def parse_format_response(answer: str, text_length: int | None = None):
    """Parse Groq output; distinguish a deliberate no-op from a malformed reply."""
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Groq вернул пустой ответ.")
    raw = answer.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq вернул некорректный JSON (позиция %s): %s"
            % (exc.pos, raw[:500])
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("Groq вернул JSON не в виде объекта.")
    if payload.get("no_changes") is True:
        reason = str(payload.get("reason") or "").strip()
        return None, reason or "Оформление абзацев уже выглядит согласованным."
    suggestion = validate_format_suggestion(payload)
    if text_length is not None:
        for span in suggestion.get("character_formats", []):
            if span["end"] > text_length:
                raise ValueError("ИИ указал диапазон символьного форматирования за пределами выделения.")
    return suggestion, None


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
            paragraph_text = str(paragraph.Range.Text or "").rstrip("\r\x07")
            whitespace = {
                "multiple_space_runs": len(re.findall(r" {2,}", paragraph_text)),
                "tabs": paragraph_text.count("\t"),
                "leading_spaces": len(paragraph_text) - len(paragraph_text.lstrip(" ")),
                "trailing_spaces": len(paragraph_text) - len(paragraph_text.rstrip(" ")),
            }
            character_format = {}
            for property_name in ("Bold", "Italic", "Underline"):
                try:
                    numeric_value = int(getattr(paragraph.Range.Font, property_name))
                    character_format[property_name.lower()] = "mixed" if numeric_value == 9999999 else numeric_value
                except Exception:
                    character_format[property_name.lower()] = "unknown"
            character_runs = []
            char_ranges = paragraph.Range.Characters
            for char_index in range(1, char_ranges.Count + 1):
                char_range = char_ranges.Item(char_index)
                flags = {}
                for property_name in ("Bold", "Italic", "Underline"):
                    try:
                        flags[property_name.lower()] = bool(getattr(char_range.Font, property_name))
                    except Exception:
                        flags[property_name.lower()] = None
                absolute_start = max(int(char_range.Start), int(word_range.Start))
                absolute_end = min(int(char_range.End), int(word_range.End))
                if absolute_end <= absolute_start:
                    continue
                relative_start = absolute_start - int(word_range.Start)
                relative_end = absolute_end - int(word_range.Start)
                if (character_runs and character_runs[-1]["end"] == relative_start
                        and all(character_runs[-1].get(key) == value for key, value in flags.items())):
                    character_runs[-1]["end"] = relative_end
                else:
                    character_runs.append({"start": relative_start, "end": relative_end, **flags})
            profiles.append({
                "paragraph": index,
                "character_runs": character_runs,
                "style": style_name[:80],
                "whitespace": whitespace,
                "character_format": character_format,
                "alignment": int(fmt.Alignment),
                "left_indent_pt": round(float(fmt.LeftIndent), 2),
                "right_indent_pt": round(float(fmt.RightIndent), 2),
                "first_line_indent_pt": round(float(fmt.FirstLineIndent), 2),
                "space_before_pt": round(float(fmt.SpaceBefore), 2),
                "space_after_pt": round(float(fmt.SpaceAfter), 2),
            })
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
            paragraph_suggestions = None
            if "paragraphs" in suggestion:
                paragraph_suggestions = {
                    item["paragraph"]: {key: value for key, value in item.items() if key != "paragraph"}
                    for item in suggestion["paragraphs"]
                }
            for index in range(1, paragraphs.Count + 1):
                paragraph = paragraphs.Item(index)
                current_suggestion = paragraph_suggestions.get(index) if paragraph_suggestions is not None else {
                    key: value for key, value in suggestion.items()
                    if key not in ("paragraphs", "character_formats")
                }
                if not current_suggestion:
                    continue
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
                if "alignment" in current_suggestion:
                    fmt.Alignment = _WORD_ALIGNMENTS[current_suggestion["alignment"]]
                if "left_indent_pt" in current_suggestion:
                    fmt.LeftIndent = current_suggestion["left_indent_pt"]
                if "right_indent_pt" in current_suggestion:
                    fmt.RightIndent = current_suggestion["right_indent_pt"]
                if "first_line_indent_pt" in current_suggestion:
                    fmt.FirstLineIndent = current_suggestion["first_line_indent_pt"]
                if "space_before_pt" in current_suggestion:
                    fmt.SpaceBefore = current_suggestion["space_before_pt"]
                if "space_after_pt" in current_suggestion:
                    fmt.SpaceAfter = current_suggestion["space_after_pt"]
                applied += 1

            for span in suggestion.get("character_formats", []):
                char_range = document.Range(start + span["start"], start + span["end"])
                font = char_range.Font
                if "bold" in span:
                    font.Bold = span["bold"]
                if "italic" in span:
                    font.Italic = span["italic"]
                if "underline" in span:
                    # Word wdUnderlineNone=0, wdUnderlineSingle=1.
                    font.Underline = 1 if span["underline"] else 0
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
    if "paragraphs" in suggestion:
        for item in suggestion["paragraphs"]:
            for key, value in item.items():
                if key == "paragraph":
                    continue
                shown = values.get(value, f"{value:g} пт" if isinstance(value, float) else str(value))
                lines.append(f"• Абзац {item['paragraph']} — {labels[key]}: {shown}")
    else:
        for key, value in suggestion.items():
            if key in ("paragraphs", "character_formats"):
                continue
            shown = values.get(value, f"{value:g} пт" if isinstance(value, float) else str(value))
            lines.append(f"• {labels[key]}: {shown}")
    for span in suggestion.get("character_formats", []):
        props = []
        for key, label in (("bold", "жирный"), ("italic", "курсив"), ("underline", "подчёркивание")):
            if key in span:
                props.append(label if span[key] else "без " + label)
        lines.append(f"• Символы {span['start']}–{span['end']}: " + ", ".join(props))
    return "\n".join(lines)



def _build_analysis_messages(selected_text: str, profiles: list[dict]) -> list[dict]:
    """Evaluate visual suitability as well as consistency of paragraph settings."""
    profile_json = json.dumps(profiles, ensure_ascii=False)
    system = (
        "Ты — редактор визуального оформления документов Word. Оцени не только "
        "единообразие параметров, но и то, насколько оформление удобно читать и "
        "соответствует назначению текста. Все абзацы могут быть одинаково оформлены, "
        "но при этом нуждаться в улучшении. Учитывай содержание, длину, количество "
        "абзацев, вероятные роли и текущие параметры. Не меняй текст, смысл, шрифт, "
        "размер или цвет. "
        "Разрешены только свойства абзацев: alignment (left/center/right/justify), "
        "left_indent_pt, right_indent_pt, first_line_indent_pt, space_before_pt, "
        "space_after_pt. Числа — в пунктах. Для обычного основного текста боковые "
        "отступы обычно 0; выравнивание слева или по ширине. Обычно выбирают один "
        "подход: отступ первой строки около 18 пт ИЛИ интервал после абзаца около 6 пт, "
        "не оба одновременно без причины. Для нескольких коротких/средних абзацев "
        "основного текста с нулевыми интервалами и без отступа первой строки рассмотри "
        "space_after_pt=6: это улучшает разделение даже при одинаковых исходных настройках. "
        "Не навязывай интервал для одного абзаца, заголовков, адресов, коротких подписей, "
        "стихов, таблицеподобных строк и намеренно плотных блоков. Не применяй выравнивание "
        "по ширине к коротким строкам; не центрируй обычный текст. Не предлагай косметику "
        "без ощутимой пользы. Если есть конкретное улучшение, верни JSON только с "
        "изменяемыми полями и итоговыми значениями. Если после оценки качества улучшение "
        "не нужно, верни строго "
        '{"no_changes":true,"reason":"краткое объяснение"}. '
        "Если меняются не все абзацы или значения различаются, используй формат "
        '{"paragraphs":[{"paragraph":1,"space_after_pt":6},'
        '{"paragraph":2,"alignment":"left"}]}. Номер абзаца — номер из профиля. '
        "Если одно изменение подходит всем, также можно вернуть общий объект. "
        "Учитывай character_runs каждого абзаца: start/end — смещения символов "
        "от начала выделения, bold/italic/underline — текущее оформление. "
        "Если заголовок, ключевой термин или важное обозначение следует выделить, "
        "можешь предложить символьное оформление точного диапазона. Формат: "
        '{"character_formats":[{"start":0,"end":12,"bold":true},'
        '{"start":20,"end":34,"italic":true}]}. '
        "Смещения нулевые, end не включается. Предлагай только нужные свойства, "
        "не сбрасывай остальные; не форматируй подряд весь текст без причины. "
        "Никогда не меняй текст, смысл, шрифт, размер или цвет. "
        "Не возвращай пустой объект. Только JSON без Markdown. Безопасные пределы: "
        "отступы -36..144 пт, интервалы 0..48 пт."
    )
    user = (
        "Оцени оформление фрагмента. Важно: одинаковые значения во всех абзацах "
        "сами по себе НЕ являются причиной отвечать no_changes. Проверь, не выглядит "
        "ли основной текст слитным из-за нулевых интервалов, нужны ли умеренные "
        "интервалы между абзацами и соответствует ли выравнивание типу содержимого. "
        "Определи структуру текста и предложи только полезные изменения.\n\n"
        "Текст выделения:\n" + selected_text
        + "\n\nПараметры абзацев (пункты):\n" + profile_json
        + "\n\nВерни только JSON согласно системной инструкции."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def open_word_formatter(parent):
    """Analyze the current Word selection immediately and apply safe formatting suggestions."""
    print("[Word] Запущена команда форматирования выделения.", flush=True)
    try:
        start, end, document_identity, selected_text, profiles = _word_selection_snapshot()
        print(
            "[Word] Выделение прочитано: диапазон=%s:%s, документ=%r, символов=%s, абзацев=%s."
            % (start, end, document_identity, len(selected_text), len(profiles)),
            flush=True,
        )
    except Exception as exc:
        print("[Word] Не удалось прочитать выделение: %s: %s" % (type(exc).__name__, exc), flush=True)
        messagebox.showerror("ИИ — подровнять Word", str(exc), parent=parent)
        return

    print("[Word] Выделение автоматически отправляется на анализ по нажатию кнопки.", flush=True)

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
            print(
                "[Word] Начат анализ: символов=%s, абзацев=%s, профили=%s."
                % (len(selected_text), len(profiles), json.dumps(profiles, ensure_ascii=False)),
                flush=True,
            )
            messages = _build_analysis_messages(selected_text, profiles)
            print("[Word] Отправка запроса в Groq (JSON mode).", flush=True)
            answer = chat(messages, temperature=0.1, max_tokens=600,
                          response_format={"type": "json_object"})
            print("[Word] Получен ответ Groq: %s символов; фрагмент=%r."
                  % (len(answer), answer[:1200]), flush=True)
            suggestion, no_change_reason = parse_format_response(answer, len(selected_text))
            if suggestion is None:
                print("[Word] Изменения не требуются: " + no_change_reason, flush=True)
                result = (None, None, no_change_reason)
            else:
                print("[Word] Предложение проверено: "
                      + json.dumps(suggestion, ensure_ascii=False), flush=True)
                result = (suggestion, None, None)
        except Exception as exc:
            print("[Word] Ошибка анализа: %s: %s" % (type(exc).__name__, exc), flush=True)
            result = (None, str(exc), None)

        def finish():
            try:
                progress.destroy()
            except tk.TclError:
                pass
            suggestion, error, no_change_reason = result
            if error:
                messagebox.showerror("ИИ — подровнять Word", error, parent=parent)
                return
            if suggestion is None:
                messagebox.showinfo(
                    "ИИ — подровнять Word",
                    no_change_reason or "Оформление уже выглядит согласованным. Изменения не нужны.",
                    parent=parent,
                )
                return
            print("[Word] Предложение ИИ: " + _format_summary(suggestion), flush=True)
            try:
                count = _apply_to_word(start, end, document_identity, selected_text, suggestion)
            except Exception as exc:
                print("[Word] Ошибка применения: %s: %s" % (type(exc).__name__, exc), flush=True)
                messagebox.showerror("ИИ — подровнять Word", str(exc), parent=parent)
                return
            print("[Word] Применение завершено: операций форматирования=%s." % count, flush=True)
            if count == 0:
                messagebox.showwarning(
                    "ИИ — подровнять Word",
                    "Не найдено обычных абзацев для изменения. Заголовки и списки не затронуты.",
                    parent=parent,
                )
            else:
                messagebox.showinfo(
                    "Готово",
                    f"Форматирование применено. Операций: {count}. "
                    "Изменения можно отменить в Word сочетанием Ctrl+Z. Документ не сохранён автоматически.",
                    parent=parent,
                )

        try:
            parent.after(0, finish)
        except tk.TclError:
            pass

    threading.Thread(target=analyze, daemon=True, name="word-format-ai").start()
    print("[Word] Фоновый поток анализа запущен.", flush=True)
