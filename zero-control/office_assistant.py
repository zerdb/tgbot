"""AI commands for the currently frontmost Microsoft Word or Excel window."""
from __future__ import annotations
import json
import re


def _find_office_window():
    import psutil
    import win32gui
    import win32process
    matches = []
    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd).strip():
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = psutil.Process(pid).name().upper()
        except (psutil.Error, OSError):
            return True
        if name in ("EXCEL.EXE", "WINWORD.EXE"):
            matches.append({"pid": pid, "process": name, "title": win32gui.GetWindowText(hwnd)})
            return False
        return True
    win32gui.EnumWindows(visit, None)
    if not matches:
        raise RuntimeError("Не найдено открытое окно Microsoft Word или Excel.")
    return matches[0]


def _connect(target):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    prog_id = "Excel.Application" if target["process"] == "EXCEL.EXE" else "Word.Application"
    try:
        app = win32com.client.GetActiveObject(prog_id)
    except Exception as exc:
        raise RuntimeError("Не удалось подключиться к открытому приложению Office.") from exc
    try:
        import win32process
        _, pid = win32process.GetWindowThreadProcessId(int(app.Hwnd))
        if pid != target["pid"]:
            raise RuntimeError("Найдено несколько экземпляров Office; COM подключился не к тому окну. Закрой лишний экземпляр.")
    except RuntimeError:
        raise
    except Exception:
        pass
    return app


def _context(app, is_excel):
    if is_excel:
        book, sheet, selection = app.ActiveWorkbook, app.ActiveSheet, app.Selection
        if book is None:
            raise RuntimeError("В Excel нет активной книги.")
        values = []
        try:
            for r in range(1, min(int(selection.Rows.Count), 15) + 1):
                values.append([
                    str(selection.Cells(r, c).Value or "")[:120]
                    for c in range(1, min(int(selection.Columns.Count), 8) + 1)
                ])
        except Exception:
            pass
        return {"application":"Excel", "workbook":str(book.Name),
                "sheet":str(sheet.Name), "selection":str(getattr(selection,"Address","")),
                "selected_values":values}
    doc, selection = app.ActiveDocument, app.Selection
    if doc is None:
        raise RuntimeError("В Word нет активного документа.")
    selected = str(selection.Text or "")
    return {"application":"Word", "document":str(doc.Name),
            "selection_text":selected[:4000], "has_selection":bool(selected.strip())}


def _plan(command, context):
    from groq_client import chat
    system = (
        "Ты планировщик действий ТОЛЬКО для Microsoft Word и Excel. Верни только JSON "
        'формата {"actions":[...],"message":"кратко"}. '
        "Excel actions: "
        '{"type":"sum_column","column":"B"} (добавить формулу SUM под последними данными); '
        '{"type":"format_cell","cell":"C5","bold":true,"italic":false,"fill_color":"#FF0000"}; '
        '{"type":"format_range","range":"A1:C3","bold":true,"fill_color":"#FF0000"}; '
        '{"type":"set_formula","cell":"D2","formula":"=A2+B2"}; '
        '{"type":"set_value","cell":"A1","value":"текст"}. '
        "Word action: "
        '{"type":"format_selection","bold":true,"italic":true,"underline":true} '
        "(только текущее выделение). Не менять текст Word, выравнивание, отступы, "
        "интервалы, шрифты или размеры. Не использовать макросы, VBA, произвольный код "
        "или внешние ссылки. Если пользователь произносит букву столбца по-русски (например, «Б»), " 
        "преобразуй её в соответствующую латинскую букву Excel (B). Не угадывай адрес ячейки. " 
        "Если неясно/не поддерживается, "
        'верни {"actions":[],"message":"что нужно уточнить"}.'
    )
    answer = chat([
        {"role":"system","content":system},
        {"role":"user","content":json.dumps({"command":command,"context":context},ensure_ascii=False)}
    ], temperature=0, max_tokens=700, timeout=60, response_format={"type":"json_object"})
    try:
        plan = json.loads(answer.strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError("ИИ вернул некорректный план действий.") from exc
    if not isinstance(plan,dict) or not isinstance(plan.get("actions"),list):
        raise RuntimeError("ИИ не вернул список действий.")
    if not plan["actions"]:
        raise RuntimeError(str(plan.get("message") or "Для этой команды нет подходящего действия."))
    if len(plan["actions"]) > 8:
        raise RuntimeError("В одной команде допускается не более 8 действий.")
    return plan


def _font(font, action):
    for prop in ("bold","italic","underline"):
        if prop in action:
            if not isinstance(action[prop],bool):
                raise ValueError("Параметр %s должен быть true/false." % prop)
            setattr(font,prop.capitalize(),action[prop])


def _cell(value):
    value = str(value or "").strip().replace("$","")
    if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}",value,re.I):
        raise ValueError("Некорректный адрес ячейки.")
    return value.upper()


def _excel_apply(app, actions):
    sheet, results = app.ActiveSheet, []
    for action in actions:
        kind = action.get("type")
        if kind == "sum_column":
            col = str(action.get("column") or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{1,3}",col):
                raise ValueError("Укажи столбец, например B.")
            last = int(sheet.Range("%s%d" % (col, int(sheet.Rows.Count))).End(-4162).Row)
            if last < 1 or sheet.Range("%s%d" % (col,last)).Value in (None,""):
                raise ValueError("Указанный столбец пуст.")
            last_cell = sheet.Range("%s%d" % (col,last))
            existing_formula = str(last_cell.Formula or "").replace(" ", "").upper()
            if existing_formula.startswith("=SUM("):
                last -= 1
            first_value = sheet.Range("%s1" % col).Value
            first = 2 if isinstance(first_value,str) and first_value.strip() else 1
            if first > last:
                raise ValueError("В столбце нет данных для суммы.")
            if last >= int(sheet.Rows.Count):
                raise ValueError("В столбце нет свободной строки для результата.")
            row = last + 1
            result_cell = sheet.Range("%s%d" % (col,row))
            result_cell.Formula = "=SUM(%s%d:%s%d)" % (col,first,col,last)
            result_cell.Font.Bold = True
            results.append("Сумма столбца %s записана в %s%d" % (col,col,row))
        elif kind == "format_cell":
            address = _cell(action.get("cell"))
            target = sheet.Range(address)
            _font(target.Font,action)
            if "fill_color" in action:
                color = str(action["fill_color"])
                if not re.fullmatch(r"#[0-9A-Fa-f]{6}",color):
                    raise ValueError("Цвет должен быть в формате #RRGGBB.")
                red,green,blue = (int(color[i:i+2],16) for i in (1,3,5))
                target.Interior.Color = red + green*256 + blue*65536
            results.append("Оформлена ячейка "+address)
        elif kind == "format_range":
            address = str(action.get("range") or "").strip().replace("$","")
            if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}(?::[A-Z]{1,3}[1-9][0-9]{0,6})?",address,re.I):
                raise ValueError("Некорректный диапазон.")
            target = sheet.Range(address)
            _font(target.Font,action)
            if "fill_color" in action:
                color = str(action["fill_color"])
                if not re.fullmatch(r"#[0-9A-Fa-f]{6}",color):
                    raise ValueError("Цвет должен быть в формате #RRGGBB.")
                red,green,blue = (int(color[i:i+2],16) for i in (1,3,5))
                target.Interior.Color = red + green*256 + blue*65536
            results.append("Оформлен диапазон "+address.upper())
        elif kind == "set_formula":
            address, formula = _cell(action.get("cell")), str(action.get("formula") or "").strip()
            allowed_functions = {
                "SUM","AVERAGE","MIN","MAX","COUNT","COUNTA","IF","AND","OR",
                "ROUND","ROUNDUP","ROUNDDOWN","ABS","TODAY","NOW",
            }
            functions = re.findall(r"([A-Z][A-Z0-9_.]*)\s*\(", formula.upper())
            if (not formula.startswith("=") or len(formula)>250 or "!" in formula or
                "[" in formula or "]" in formula or
                any(name not in allowed_functions for name in functions)):
                raise ValueError("Формула отклонена: разрешены только простые формулы и стандартные функции.")
            sheet.Range(address).Formula = formula
            results.append("Формула записана в "+address)
        elif kind == "set_value":
            address, value = _cell(action.get("cell")), action.get("value")
            if not isinstance(value,(str,int,float,bool)) and value is not None:
                raise ValueError("Недопустимое значение.")
            if isinstance(value,str) and (len(value)>2000 or value.startswith("=")):
                raise ValueError("Слишком длинный текст или формула в поле значения.")
            sheet.Range(address).Value = value
            results.append("Значение записано в "+address)
        else:
            raise ValueError("Неизвестное действие Excel: "+str(kind))
    return results


def _word_apply(app, actions):
    selection = app.Selection
    if not str(selection.Text or "").strip():
        raise RuntimeError("Сначала выдели текст в Word.")
    results = []
    for action in actions:
        if action.get("type") != "format_selection":
            raise ValueError("Это действие Word пока не поддерживается.")
        font = selection.Font
        for prop in ("bold","italic"):
            if prop in action:
                if not isinstance(action[prop],bool):
                    raise ValueError("Параметр %s должен быть true/false." % prop)
                setattr(font,prop.capitalize(),action[prop])
        if "underline" in action:
            if not isinstance(action["underline"],bool):
                raise ValueError("Параметр underline должен быть true/false.")
            font.Underline = 1 if action["underline"] else 0
        results.append("Оформлено текущее выделение Word")
    return results


def execute_office_command(command):
    """Detect the frontmost Office window, build a constrained plan and execute it."""
    command = str(command or "").strip()
    if not command:
        raise ValueError("Пустая команда.")
    target = _find_office_window()
    app = _connect(target)
    is_excel = target["process"] == "EXCEL.EXE"
    context = _context(app,is_excel)
    plan = _plan(command,context)
    results = _excel_apply(app,plan["actions"]) if is_excel else _word_apply(app,plan["actions"])
    return str(plan.get("message") or "Готово.") + "\n" + "\n".join("• "+x for x in results)
