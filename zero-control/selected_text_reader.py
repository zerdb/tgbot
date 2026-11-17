"""Чтение выделенного текста через Windows UI Automation без clipboard."""
from __future__ import annotations


def get_selected_text() -> str:
    """Возвращает выделение активного приложения через UIA TextPattern.

    Буфер обмена не читается и не изменяется. Если приложение не предоставляет
    UI Automation TextPattern или выделение пустое, возвращается пустая строка.
    """
    import pythoncom
    import uiautomation as automation

    pythoncom.CoInitialize()
    try:
        control = automation.GetFocusedControl()
        text_pattern_id = automation.PatternId.TextPattern

        # В некоторых приложениях фокус находится на дочернем элементе,
        # а TextPattern реализован родительским документом/редактором.
        for _ in range(16):
            if control is None:
                break
            try:
                pattern = control.GetPattern(text_pattern_id)
                if pattern is not None:
                    ranges = pattern.GetSelection()
                    selected = [item.GetText(-1) for item in ranges]
                    text = "\n".join(part for part in selected if part).strip()
                    if text:
                        return text
            except Exception:
                # Не каждый элемент и не каждое приложение поддерживают TextPattern.
                pass
            try:
                control = control.GetParentControl()
            except Exception:
                break
        return ""
    finally:
        pythoncom.CoUninitialize()
