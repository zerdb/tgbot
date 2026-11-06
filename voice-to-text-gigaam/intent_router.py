"""Ollama Cloud semantic intent classification; execution stays in local Python."""
from __future__ import annotations
import json, re
ACTIONS = {
 "add_contact": "Добавить нового человека в локальную адресную книгу контактов и открыть пустую карточку.",
 "open_contacts": "Открыть общую адресную книгу контактов.",
 "open_assistant_settings": "Открыть настройки GigaAM.",
 "read_unread_mail": "Прочитать и кратко пересказать непрочитанные письма через IMAP и ИИ.",
 "ai_chat": "Ответить на вопрос пользователя через подключённую языковую модель; question — полный вопрос.",
 "email_compose": "Создать письмо; если просят отправить/прикрепить файл, attach_copied_files=true.",
 "camera_question": "Получить свежий кадр камеры и ответить на вопрос пользователя по изображению; question — вопрос.",
 "save_note": "Сохранить буфер обмена как заметку.",
 "add_note": "Сохранить произнесённый текст как заметку без срока; note_text — текст записи.",
 "complete_item": "Отметить заметку или дело выполненным; item_text — фрагмент текста записи.",
 "clipboard_to_excel": "Создать Excel из данных буфера обмена.",
 "lock_computer": "Заблокировать компьютер.",
 "reboot_computer": "Перезагрузить компьютер.",
 "open_downloads": "Открыть папку Загрузки.",
 "open_recycle_bin": "Открыть Корзину Windows для просмотра; не очищать её.",
 "open_application": "Открыть приложение из разрешённого списка; app — notepad, calculator, browser, word, excel или images.",
 "open_settings": "Открыть настройки Windows.",
 "empty_recycle_bin": "Очистить корзину.",
 "screenshot": "Сделать скриншот.",
 "reminder": "Создать напоминание; reminder_text сохранить равным исходной фразе.",
 "organize_folder": "Открыть мастер сортировки файлов.",
 "open_reminders": "Открыть общий список заметок, дел и напоминаний.",
 "open_mail_client": "Открыть почтовый клиент.",
 "search_web": "Поискать информацию в интернете; query — предмет поиска.",
 "search_files": "Найти файл или папку на компьютере; query — имя/описание.",
 "unknown": "Неясная или неподдерживаемая задача."
}
SYSTEM_PROMPT = """Ты — классификатор намерений русскоязычного Windows-помощника.
Понимай смысл фразы, не требуй точных шаблонов. Выбери ровно одно действие из списка.
Верни только JSON: action, confidence (0..1), arguments.
Допустимые аргументы: attach_copied_files (boolean), reminder_text (string), note_text (string), item_text (string), query (string), question (string), app (string).\nЕсли пользователь хочет задать вопрос ИИ, получить объяснение, совет или справку, а не выполнить действие на компьютере — выбери ai_chat и передай полный вопрос в question. Формулировки «спроси ИИ» и «задай вопрос нейросети» явно означают ai_chat.
Если пользователь хочет добавить/сохранить человека в контакты или адресную книгу — выбери add_contact.
Если пользователь просит показать, открыть или посмотреть список контактов — выбери open_contacts.
Фразы «добавь в контакты», «добавь контакт», «сохрани в адресную книгу», «запиши контакт» означают add_contact.
Просьба отправить/переслать файл или документ по почте => email_compose и attach_copied_files=true.
Просто создать письмо => email_compose и attach_copied_files=false.
Для напоминания передай исходную фразу в reminder_text. Если пользователь говорит «запомни», «сохрани заметку» с произнесённым текстом или «добавь запись», выбери add_note и передай текст в note_text. Если просит отметить запись выполненной, выбери complete_item и передай название или фрагмент в item_text.
Если просят открыть корзину/мусорное ведро — open_recycle_bin, НЕ open_downloads и НЕ empty_recycle_bin.
Если просят очистить/опустошить корзину — empty_recycle_bin.
Блокнот — open_application app="notepad"; калькулятор — app="calculator"; браузер — app="browser"; Word — app="word"; Excel — app="excel"; папка Изображения/Картинки/Фото — app="images".
Не путай корзину с загрузками. Неясная задача => unknown. Не придумывай действия и параметры.
Доступные действия: """ + json.dumps(ACTIONS, ensure_ascii=False)

def _is_natural_information_question(text: str) -> bool:
    """Route conversational questions to AI without requiring an AI keyword."""
    normalized = re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()
    if not normalized:
        return False
    action_request = re.search(
        r"\b(открой|открыть|запусти|запустить|сделай|сделать|найди файл|найти файл|"
        r"создай напоминание|напомни|заблокируй|перезагрузи|очисти корзину|"
        r"сохрани как заметку|создай письмо|добавь контакт|разбери папку|напомни|отправь|отправить)\b",
        normalized,
    )
    if action_request:
        return False
    cues = (
        "что за ", "почему", "зачем", "как ", "кто ", "где ", "когда ",
        "какой ", "какая ", "какие ", "какое ", "сколько", "в чем смысл",
        "в чём смысл", "что означает", "что значит", "объясни", "расскажи",
        "правда ли", "можно ли", "откуда", "для чего", "чем отличается",
    )
    return "?" in normalized or any(cue in normalized for cue in cues)


def understand_command(user_text: str) -> dict:
    normalized = re.sub(r"\s+", " ", (user_text or "").lower().replace("ё", "е")).strip(" .,!?:;")

    # Разделяем настройки Windows и настройки самого помощника.
    if re.search(r"\b(настройки windows|параметры windows|системные настройки|параметры системы)\b", normalized):
        return {"action": "open_settings", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть|покажи|показать|зайди в|перейди в)\b.*\b(настройк)", normalized) or normalized in ("настройки", "настройки помощника"):
        return {"action": "open_assistant_settings", "confidence": 1.0, "arguments": {}}

    # Простые команды адресной книги обрабатываем локально: они не должны
    # зависеть от доступности Ollama Cloud или точности ответа классификатора.
    if re.search(r"\b(добавь|добавить|запиши|записать|сохрани|сохранить)\b.*\b(в контакты|контакт|адресную книгу)\b|\b(добавь|добавить)\s+в\s+контакты\b", normalized):
        return {"action": "add_contact", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть|покажи|показать|посмотри|просмотреть)\b.*\b(контакты|адресную книгу)\b", normalized):
        return {"action": "open_contacts", "confidence": 1.0, "arguments": {}}
    # Локальная маршрутизация поддерживаемых команд: обычные действия не зависят от квоты Ollama Cloud.
    if re.search(r"\b(разбери|разобрать|рассортируй|отсортируй|организуй)\b.*\b(папк|файл|документ)", normalized):
        return {"action": "organize_folder", "confidence": 1.0, "arguments": {}}

    # Голосовое управление общей системой заметок и дел.
    done_match = re.search(r"\b(отметь|пометь|закрой)\b\s+(.+?)\s+(?:выполненным|выполненной|готовым|сделанным)$", normalized)
    if done_match:
        return {"action": "complete_item", "confidence": 1.0, "arguments": {"item_text": done_match.group(2).strip()}}
    note_match = re.match(r"^(?:запомни|сохрани заметку|добавь заметку|добавь запись)\s+(.+)$", normalized)
    if note_match:
        return {"action": "add_note", "confidence": 1.0, "arguments": {"note_text": note_match.group(1).strip()}}
    # Открытие раздела напоминаний и создание нового напоминания — разные намерения.
    if re.search(r"\b(открой|покажи|открыть|посмотреть)\b.*\b(напоминан|заметк|дела|задач)", normalized):
        return {"action": "open_reminders", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(напомни|напомнить|создай напоминание|добавь напоминание)\b", normalized):
        return {"action": "reminder", "confidence": 1.0, "arguments": {"reminder_text": user_text.strip()}}

    # Почта: создание/отправка письма открывает форму; само отправление только после кнопки пользователя.
    if re.search(r"\b(отправь|отправить|перешли|переслать)\b.*\b(почт|письм|email|емейл)", normalized):
        attach = bool(re.search(r"\b(файл|файлы|документ|документы|вложени)", normalized))
        return {"action": "email_compose", "confidence": 1.0, "arguments": {"attach_copied_files": attach}}
    if re.search(r"\b(создай|создать|напиши|написать|составь|составить)\b.*\b(письмо|письмецо|email)", normalized):
        return {"action": "email_compose", "confidence": 1.0, "arguments": {"attach_copied_files": False}}
    if re.search(r"\b(открой|открыть|покажи)\b.*\b(почту|почтовый клиент|входящие)", normalized):
        return {"action": "open_mail_client", "confidence": 1.0, "arguments": {}}

    # Частые приложения из разрешённого списка.
    app_patterns = (
        (r"\b(блокнот|notepad)\b", "notepad"),
        (r"\b(калькулятор|calculator)\b", "calculator"),
        (r"\b(браузер|интернет|google|хром|chrome)\b", "browser"),
        (r"\b(word|ворд|микрософт ворд)\b", "word"),
        (r"\b(excel|эксель)\b", "excel"),
        (r"\b(изображения|картинки|фото)\b", "images"),
    )
    if re.search(r"\b(открой|открыть|запусти|запустить)\b", normalized):
        for pattern, app in app_patterns:
            if re.search(pattern, normalized):
                return {"action": "open_application", "confidence": 1.0, "arguments": {"app": app}}

    if re.search(r"\b(открой|открыть|покажи)\b.*\b(загрузки|загруженные файлы)", normalized):
        return {"action": "open_downloads", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть|покажи)\b.*\b(корзину|корзина)", normalized):
        return {"action": "open_recycle_bin", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(очисти|очистить|опустоши|опустошить)\b.*\b(корзину|корзина)", normalized):
        return {"action": "empty_recycle_bin", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(заблокируй|заблокировать)\b.*\b(компьютер|ноутбук|пк)", normalized):
        return {"action": "lock_computer", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(перезагрузи|перезагрузить|перезапусти)\b.*\b(компьютер|ноутбук|пк|windows)", normalized):
        return {"action": "reboot_computer", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(сделай|сделать|сними|снять)\b.*\b(скриншот|снимок экрана)", normalized):
        return {"action": "screenshot", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть)\b.*\b(настройки windows|параметры windows)", normalized):
        return {"action": "open_settings", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(сохрани|сохранить)\b.*\b(заметк)", normalized):
        return {"action": "save_note", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(создай|сделай)\b.*\b(excel|эксель|таблицу из буфера)", normalized):
        return {"action": "clipboard_to_excel", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(найди|поищи|найти)\b.*\b(файл|папку|документ)", normalized):
        query = re.sub(r"^.*?\b(?:найди|поищи|найти)\b", "", normalized).strip()
        query = re.sub(r"\b(?:файл|папку|документ)\b", "", query).strip()
        return {"action": "search_files", "confidence": 1.0, "arguments": {"query": query or user_text.strip()}}
    if re.search(r"\b(поищи|найди|найти)\b", normalized) and re.search(r"\b(в интернете|в интернет|в сети|в google)\b", normalized):
        query = re.sub(r"^.*?\b(?:поищи|найди|найти)\b", "", normalized).strip()
        query = re.sub(r"\b(?:в интернете|в интернет|в сети|в google)\b", "", query).strip()
        return {"action": "search_web", "confidence": 1.0, "arguments": {"query": query or user_text.strip()}}

    # Вопросы о наблюдении отправляем на анализ свежего кадра.
    camera_context = re.search(r"\b(камера|камере|камеру|видеонаблюдени|на парковке|во дворе|у ворот|в кадре|на изображении|на видео|на записи|там|здесь|тут|картинк)\b", normalized)
    camera_question = re.search(r"\b(что|кто|сколько|есть|видно|видишь|опиши|день|ночь|машин|людей|человек|сейчас)\b", normalized)
    if camera_context and camera_question:
        return {"action": "camera_question", "confidence": 1.0, "arguments": {"question": user_text.strip()}}
    if re.search(r"\b(настройки помощника|настройки gigaam|настройки гигаам)\b", normalized):
        return {"action": "open_assistant_settings", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(прочитай|проверь|покажи)\b.*\b(новые|непрочитанные)\b.*\b(письма|почту)\b", normalized):
        return {"action": "read_unread_mail", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(найди|поищи|поиск)\b.*\b(в документах|в содержимом|в файлах)\b", normalized):
        return {"action": "search_documents", "confidence": 1.0, "arguments": {}}
    if _is_natural_information_question(user_text):
        return {"action": "ai_chat", "confidence": 0.99, "arguments": {"question": user_text.strip()}}
    payload = {"messages": [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":user_text[:4000]}]}
    try:
        from ollama_client import chat
        content = chat(payload["messages"], temperature=0, max_tokens=500)
        match = re.search(r"\{.*\}", str(content or ""), flags=re.S)
        if not match:
            raise RuntimeError("Ollama Cloud вернула некорректный JSON.")
        parsed = json.loads(match.group(0))
        print("[Команды] Классификация через Ollama Cloud.", flush=True)
    except Exception as primary_error:
        print("[Команды] Ollama Cloud недоступна (%s). Пробую Moondream." % primary_error, flush=True)
        try:
            from moondream_client import chat as moondream_chat
            content = moondream_chat(payload["messages"], temperature=0, max_tokens=500)
            match = re.search(r"\{.*\}", content, flags=re.S)
            if not match:
                raise RuntimeError("Moondream вернула некорректный JSON.")
            parsed = json.loads(match.group(0))
            print("[Команды] Классификация через резервную Moondream.", flush=True)
        except Exception as fallback_error:
            raise RuntimeError("Ollama Cloud: %s; Moondream: %s" % (primary_error, fallback_error)) from fallback_error
    action = parsed.get("action", "unknown")
    if action not in ACTIONS: action = "unknown"
    try: confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError): confidence = 0.0
    raw = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
    safe = {k:v for k,v in raw.items() if k in ("attach_copied_files","reminder_text","note_text","item_text","query","question","app") and isinstance(v,(str,bool))}
    return {"action":action,"confidence":confidence,"arguments":safe}