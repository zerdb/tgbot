"""OpenRouter semantic intent classification; execution stays in local Python."""
from __future__ import annotations
import json, os, re, urllib.error, urllib.request
ACTIONS = {
 "email_compose": "Создать письмо; если просят отправить/прикрепить файл, attach_copied_files=true.",
 "save_note": "Сохранить буфер обмена как заметку.",
 "clipboard_to_excel": "Создать Excel из данных буфера обмена.",
 "lock_computer": "Заблокировать компьютер.",
 "reboot_computer": "Перезагрузить компьютер.",
 "open_downloads": "Открыть папку Загрузки.",
 "open_settings": "Открыть настройки Windows.",
 "empty_recycle_bin": "Очистить корзину.",
 "screenshot": "Сделать скриншот.",
 "reminder": "Создать напоминание; reminder_text сохранить равным исходной фразе.",
 "organize_folder": "Открыть мастер сортировки файлов.",
 "search_web": "Поискать информацию в интернете; query — предмет поиска.",
 "search_files": "Найти файл или папку на компьютере; query — имя/описание.",
 "unknown": "Неясная или неподдерживаемая задача."
}
SYSTEM_PROMPT = """Ты — классификатор намерений русскоязычного Windows-помощника.
Понимай смысл фразы, не требуй точных шаблонов. Выбери ровно одно действие из списка.
Верни только JSON: action, confidence (0..1), arguments.
Допустимые аргументы: attach_copied_files (boolean), reminder_text (string), query (string).
Просьба отправить/переслать файл или документ по почте => email_compose и attach_copied_files=true.
Просто создать письмо => email_compose и attach_copied_files=false.
Для напоминания передай исходную фразу в reminder_text.
Неясная задача => unknown. Не придумывай действия и параметры.
Доступные действия: """ + json.dumps(ACTIONS, ensure_ascii=False)

def understand_command(user_text: str) -> dict:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key: raise RuntimeError("Не задана переменная OPENROUTER_API_KEY.")
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
    payload = {"model": model, "temperature": 0, "messages": [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":user_text[:4000]}]}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","HTTP-Referer":"https://github.com/zerdb/tgbot","X-Title":"GigaAM Voice Assistant"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=35) as response: data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError("OpenRouter HTTP %s: %s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("OpenRouter недоступен: %s" % exc) from exc
    choices = data.get("choices") or []
    if not choices: raise RuntimeError("OpenRouter не вернул ответ.")
    content = (choices[0].get("message") or {}).get("content") or ""
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match: raise RuntimeError("Модель вернула ответ не в формате JSON.")
    parsed = json.loads(match.group(0))
    action = parsed.get("action", "unknown")
    if action not in ACTIONS: action = "unknown"
    try: confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError): confidence = 0.0
    raw = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
    safe = {k:v for k,v in raw.items() if k in ("attach_copied_files","reminder_text","query") and isinstance(v,(str,bool))}
    return {"action":action,"confidence":confidence,"arguments":safe}