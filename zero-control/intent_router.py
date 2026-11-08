"""Groq semantic intent classification; execution stays in local Python."""
from __future__ import annotations
import json, re
ACTIONS = {
 "add_contact": "Добавить нового человека в локальную адресную книгу контактов и открыть пустую карточку.",
 "open_contacts": "Открыть общую адресную книгу контактов.",
 "open_assistant_settings": "Открыть настройки Zero Control.",
 "read_unread_mail": "Прочитать и кратко пересказать непрочитанные письма через IMAP и ИИ.",
 "ai_chat": "Ответить на вопрос пользователя через подключённую языковую модель; question — полный вопрос.",
 "email_compose": "Подготовить письмо; если просят отправить/прикрепить файлы, attach_copied_files=true. Если назван получатель, передай его имя в recipient_name.",
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
 "open_installed_application": "Найти и запустить установленное приложение Windows по его названию; app_name — название из команды пользователя.",
 "open_settings": "Открыть настройки Windows.",
 "empty_recycle_bin": "Очистить корзину.",
 "screenshot": "Сделать скриншот.",
 "inspect_screen": "Сделать свежий снимок экрана и открыть модуль его анализа.",
 "paste_clipboard_to_application": "Открыть указанную программу и вставить в неё текст из буфера обмена; app_name — название приложения.",
 "reminder": "Создать напоминание; reminder_text сохранить равным исходной фразе.",
 "organize_folder": "Открыть мастер сортировки файлов.",
 "open_reminders": "Открыть общий список заметок, дел и напоминаний.",
 "open_mail_client": "Открыть почтовый клиент.",
 "search_web": "Поискать информацию в интернете; query — предмет поиска.",
 "search_files": "Найти файл на компьютере; query — имя/описание.",
 "open_folder": "Открыть папку по названию или пути; folder — название или путь папки.",
 "unknown": "Неясная или неподдерживаемая задача."
}
SYSTEM_PROMPT = """Ты — слой понимания намерений русскоязычного Windows-помощника Zero Control.
Распознавание речи уже завершено: входной текст — результат ASR. Не исправляй его механически и не подбирай команду по совпадению отдельных слов. Восстанови наиболее вероятный смысл всей фразы с учётом контекста.
Разделяй три результата:
1) execute — пользователь хочет выполнить действие на компьютере;
2) respond — пользователь задаёт вопрос или хочет обычный ответ/объяснение;
3) clarify — намерение или обязательный параметр нельзя определить достаточно надёжно.
Верни один JSON-объект строго по контракту:
{
  "schema_version": 1,
  "kind": "execute|respond|clarify",
  "action": "одно действие из списка ниже",
  "goal": "краткая формулировка цели пользователя",
  "target": {"type": "application|file|folder|website|system|person|list|other|null", "name": "название или пустая строка", "location": "где находится/куда направить или пустая строка"},
  "source": {"type": "clipboard|spoken_text|screen|camera|email|filesystem|none|other", "name": "что именно является источником или пустая строка"},
  "method": "как выполнить действие, кратко; если несущественно — пустая строка",
  "parameters": {},
  "confidence": 0.0,
  "clarification": "один короткий уточняющий вопрос или пустая строка",
  "response": "короткий ответ пользователю для kind=respond либо пояснение для clarify; иначе пустая строка"
}
Не добавляй Markdown, комментарии или текст вне JSON.
Для совместимости дублируй параметры выполнения в объекте parameters. Допустимые ключи параметров: attach_copied_files (boolean), recipient_name (string), reminder_text (string), note_text (string), item_text (string), query (string), question (string), app (string), app_name (string), folder (string), export_format (string).
Не выдумывай отсутствующие сведения. Если пользователь просит вставить/перенести/поместить содержимое буфера, source.type=clipboard; target должен указывать приложение или место назначения, а method описывает открытие цели и вставку. Не выбирай приложение по умолчанию, если из контекста его нельзя надёжно понять: задай уточняющий вопрос (kind=clarify). Если цель явно указана — используй её независимо от формулировки глагола.
Если пользователь хочет сохранить содержимое буфера как заметку, это save_note, source.type=clipboard, target.type=list, target.name="заметки".
Если пользователь хочет сохранить произнесённый текст как заметку — add_note, source.type=spoken_text.
Если пользователь хочет задать вопрос, получить совет, объяснение или справку, выбери ai_chat и kind=respond; question должен содержать полный вопрос.
Если пользователь хочет выполнить действие, выбери kind=execute и подходящее действие из каталога.
Если действие потенциально опасное (перезагрузка, очистка корзины и т.п.), не меняй его смысл и не инициируй дополнительных действий.
Если данных недостаточно для безопасного выполнения, выбери kind=clarify и сформулируй один конкретный вопрос.
Каталог действий: """ + json.dumps(ACTIONS, ensure_ascii=False)

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


def _file_search_query(user_text: str) -> str:
    """Extract a flexible local file-search request without discarding filters."""
    query = re.sub(r"^.*?\b(?:найди|поищи|найти|поискать|где)\b", "", user_text, flags=re.IGNORECASE).strip()
    query = re.sub(
        r"\s+(?:и\s+)?(?:добавь|выгрузи|экспортируй|сохрани|запиши|сформируй|подготовь|создай|сделай\s+выгрузку)\b.*$",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\b(?:мне)\b", " ", query, flags=re.IGNORECASE)
    query = re.sub(r"\b(?:пдф|пфд|pdf)\b", ".pdf", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" .,!?:;")
    query = re.sub(r"\bдве\s+тысячи\s+двадцать\s+пять\b", "2025", query, flags=re.IGNORECASE)
    counts = {"один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10}
    digit_nouns = {"нул": "0", "единиц": "1", "дво": "2", "тро": "3", "четвер": "4", "пят": "5", "шестер": "6", "семер": "7", "восьмер": "8", "девят": "9"}
    for count_word, count in counts.items():
        for stem, digit in digit_nouns.items():
            query = re.sub(r"\b" + count_word + r"\s+" + stem + r"[а-яё]*\b", digit * count, query, flags=re.IGNORECASE)
    return query.strip()


def _understand_command_legacy(user_text: str) -> dict:
    normalized = re.sub(r"\s+", " ", (user_text or "").lower().replace("ё", "е")).strip(" .,!?:;")

    # Вопросы о текущем экране направляем в модуль снимка и анализа, а не в обычный текстовый ИИ.
    if re.search(r"\b(что|что сейчас|посмотри|посмотреть|прочитай|прочитать|опиши|увидь|видишь)\b.*\b(на экране|экран|монитор)", normalized) or normalized in ("что у меня на экране", "что видно на экране", "посмотри на экран"):
        return {"action": "inspect_screen", "confidence": 1.0, "arguments": {}}

    # Смысловые команды с буфером определяет общий классификатор по всей фразе;\n    # не перехватываем их отдельными regex-эвристиками.\n\n    # Разделяем настройки Windows и настройки самого помощника.
    if re.search(r"\b(настройки windows|параметры windows|системные настройки|параметры системы)\b", normalized):
        return {"action": "open_settings", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть|покажи|показать|зайди в|перейди в)\b.*\b(настройк)", normalized) or normalized in ("настройки", "настройки помощника"):
        return {"action": "open_assistant_settings", "confidence": 1.0, "arguments": {}}

    # Открытие произвольной папки — локальное намерение, поиск пути выполняет Python/MFT.
    folder_match = re.search(
        r"\b(?:открой|открыть|покажи|показать|зайди в|зайти в|перейди в|перейти в)\b\s+"
        r"(?:(?:мне )?(?:папку|директорию|каталог)\s+)?(.+)$",
        user_text.strip(),
        flags=re.IGNORECASE,
    )
    if folder_match and re.search(r"(папк|директор|каталог|system\s*32|system32|систем)", normalized):
        folder_name = folder_match.group(1).strip().strip('"«»').rstrip(" .,!?:;")
        folder_name = re.sub(r"^(?:папку|директорию|каталог)\s+", "", folder_name, flags=re.IGNORECASE)
        if folder_name:
            return {"action": "open_folder", "confidence": 1.0, "arguments": {"folder": folder_name}}

    # Простые команды адресной книги обрабатываем локально: они не должны
    # зависеть от доступности Groq или точности ответа классификатора.
    if re.search(r"\b(добавь|добавить|запиши|записать|сохрани|сохранить)\b.*\b(в контакты|контакт|адресную книгу)\b|\b(добавь|добавить)\s+в\s+контакты\b", normalized):
        return {"action": "add_contact", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть|покажи|показать|посмотри|просмотреть)\b.*\b(контакты|адресную книгу)\b", normalized):
        return {"action": "open_contacts", "confidence": 1.0, "arguments": {}}
    # Локальная маршрутизация поддерживаемых команд: обычные действия не зависят от квоты Groq.
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
        recipient_name = ""
        # Получатель может стоять как после слова «почту», так и перед ним:
        # «отправь на почту Шамилю» / «отправь Шамилю на почту».
        after_mail = re.search(r"\b(?:почту|почте|email|емейл)\s+(.+)$", user_text, re.IGNORECASE)
        before_mail = re.search(r"\b(?:отправь|отправить|перешли|переслать)\s+(.+?)\s+(?:на\s+)?(?:почту|почте|email|емейл)\b", user_text, re.IGNORECASE)
        candidate = (after_mail.group(1) if after_mail else before_mail.group(1) if before_mail else "").strip(" .,!?:;«»\"")
        candidate = re.sub(r"\b(?:мне|файлы?|документы?|вложения?|пожалуйста|срочно)\b", " ", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if candidate and not re.search(r"\b(?:файл|файлы|документ|документы|вложение|вложения|письмо|письма)\b", candidate, re.IGNORECASE):
            recipient_name = candidate
        return {"action": "email_compose", "confidence": 1.0, "arguments": {"attach_copied_files": attach, "recipient_name": recipient_name}}
    if re.search(r"\b(создай|создать|напиши|написать|составь|составить)\b.*\b(письмо|письмецо|email)", normalized):
        return {"action": "email_compose", "confidence": 1.0, "arguments": {"attach_copied_files": False}}
    if re.search(r"\b(открой|открыть|покажи)\b.*\b(почту|почтовый клиент|входящие)", normalized):
        return {"action": "open_mail_client", "confidence": 1.0, "arguments": {}}

    # Частые приложения из разрешённого списка.
    app_patterns = (
        (r"\b(блокнот|notepad)\b", "notepad"),
        (r"\b(калькулятор|calculator)\b", "calculator"),
        (r"\b(браузер|интернет|google|хром|chrome)\b", "browser"),
        (r"\b(word|ворд|ворт|микрософт ворд)\b", "word"),
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
    if normalized in ("скриншот", "скриншот экрана", "снимок экрана") or re.search(r"\b(сделай|сделать|сними|снять)\b.*\b(скриншот|снимок экрана)", normalized):
        return {"action": "screenshot", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(открой|открыть)\b.*\b(настройки windows|параметры windows)", normalized):
        return {"action": "open_settings", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(сохрани|сохранить)\b.*\b(заметк)", normalized):
        return {"action": "save_note", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(создай|сделай)\b.*\b(excel|эксель|таблицу из буфера)", normalized):
        return {"action": "clipboard_to_excel", "confidence": 1.0, "arguments": {}}
    # Любое другое название приложения ищем локально в меню «Пуск», на рабочем столе
    # и среди зарегистрированных приложений Windows — без обращения к языковой модели.
    open_match = re.match(
        r"^\s*(?:пожалуйста\s+)?(?:открой|открыть|запусти|запустить|включи|включить)\s+(.+?)\s*$",
        user_text.strip(),
        flags=re.IGNORECASE,
    )
    if open_match:
        app_name = open_match.group(1).strip().strip('"«»')
        app_name = re.sub(r"\s+(?:на компьютере|на пк|пожалуйста)$", "", app_name, flags=re.IGNORECASE).strip()
        if app_name and not re.search(
            r"\b(папк|директор|каталог|файл|документ|загрузк|корзин|настройк|контакт|почт|напоминан|заметк|дела|задач)\w*\b",
            app_name.lower().replace("ё", "е"),
        ):
            return {
                "action": "open_installed_application",
                "confidence": 1.0,
                "arguments": {"app_name": app_name},
            }

    # Явный поиск папки по названию — используем индекс каталогов, а не файлов.
    folder_query = re.search(r"\b(?:найди|поищи|найти|поискать)\b.*\bпапк\w*\s+(?:с\s+названи\w*\s+)?(.+)$", user_text, re.IGNORECASE)
    if folder_query and folder_query.group(1).strip():
        return {"action": "open_folder", "confidence": 1.0, "arguments": {"folder": folder_query.group(1).strip().strip("«»")}}
    # Поиск с экспортом: сначала ищем локально, затем создаём новый документ и открываем его.
    if re.search(r"\b(?:найди|поищи|найти|поискать)\b", normalized) and not re.search(
        r"\b(в интернете|в интернет|в сети|в google)\b", normalized
    ):
        export_format = None
        if re.search(r"\b(?:excel|эксель|эксел|таблиц\w*)\b", normalized):
            export_format = "excel"
        elif re.search(r"\b(?:word|ворд|docx?)\b", normalized):
            export_format = "word"
        elif re.search(r"\b(?:блокнот|notepad|текстов\w*\s+документ\w*|текстов\w*\s+файл\w*|txt)\b", normalized):
            export_format = "text"
        if export_format:
            query = _file_search_query(user_text)
            if query:
                return {
                    "action": "search_files",
                    "confidence": 1.0,
                    "arguments": {"query": query, "export_format": export_format},
                }

    # Вопросы о расположении файлов с критериями — локальный MFT-поиск,
    # а не общий вопрос к ИИ (например: «Где файлы больше 10 ГБ?»).
    file_subject = re.search(r"\b(файл\w*|документ\w*|пдф|pdf|фотографи\w*|архив\w*)\b", normalized)
    file_criteria = re.search(
        r"\b(больше|свыше|крупнее|меньше|до|созданн\w*|измененн\w*|"
        r"сегодня|вчера|прошл\w*\s+недел\w*|прошл\w*\s+месяц|"
        r"последние|новые|недавние|старые|самые большие|самые маленькие|"
        r"pdf|пдф|word|ворд|excel|эксель|презентаци\w*)\b",
        normalized,
    )
    if file_subject and file_criteria and not re.search(
        r"\b(в интернете|в интернет|в сети|в google)\b", normalized
    ):
        query = _file_search_query(user_text)
        if query:
            return {"action": "search_files", "confidence": 1.0, "arguments": {"query": query}}

    if re.search(r"\b(найди|поищи|найти|поискать)\b", normalized) and not re.search(r"\b(в интернете|в интернет|в сети|в google)\b", normalized):
        query = _file_search_query(user_text)
        if query:
            return {"action": "search_files", "confidence": 1.0, "arguments": {"query": query}}
    if re.search(r"\b(поищи|найди|найти)\b", normalized) and re.search(r"\b(в интернете|в интернет|в сети|в google)\b", normalized):
        query = re.sub(r"^.*?\b(?:поищи|найди|найти)\b", "", normalized).strip()
        query = re.sub(r"\b(?:в интернете|в интернет|в сети|в google)\b", "", query).strip()
        return {"action": "search_web", "confidence": 1.0, "arguments": {"query": query or user_text.strip()}}

    # Вопросы о наблюдении отправляем на анализ свежего кадра.
    camera_context = re.search(r"\b(камера|камере|камеру|видеонаблюдени|на парковке|во дворе|у ворот|в кадре|на изображении|на видео|на записи|там|здесь|тут|картинк)\b", normalized)
    camera_question = re.search(r"\b(что|кто|сколько|есть|видно|видишь|опиши|день|ночь|машин|людей|человек|сейчас)\b", normalized)
    if camera_context and camera_question:
        return {"action": "camera_question", "confidence": 1.0, "arguments": {"question": user_text.strip()}}
    if re.search(r"\b(настройки помощника|настройки zero control)\b", normalized):
        return {"action": "open_assistant_settings", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(прочитай|проверь|покажи)\b.*\b(новые|непрочитанные)\b.*\b(письма|почту)\b", normalized):
        return {"action": "read_unread_mail", "confidence": 1.0, "arguments": {}}
    if re.search(r"\b(найди|поищи|поиск)\b.*\b(в документах|в содержимом|в файлах)\b", normalized):
        return {"action": "search_documents", "confidence": 1.0, "arguments": {}}
    if _is_natural_information_question(user_text):
        return {"action": "ai_chat", "confidence": 0.99, "arguments": {"question": user_text.strip()}}
    payload = {"messages": [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":user_text[:4000]}]}
    try:
        from groq_client import chat
        content = chat(payload["messages"], temperature=0, max_tokens=500)
        match = re.search(r"\{.*\}", str(content or ""), flags=re.S)
        if not match:
            raise RuntimeError("Groq вернула некорректный JSON.")
        parsed = json.loads(match.group(0))
        print("[Команды] Классификация через Groq.", flush=True)
    except Exception as primary_error:
        print("[Команды] Groq недоступна (%s). Пробую Moondream." % primary_error, flush=True)
        try:
            from moondream_client import chat as moondream_chat
            content = moondream_chat(payload["messages"], temperature=0, max_tokens=500)
            match = re.search(r"\{.*\}", content, flags=re.S)
            if not match:
                raise RuntimeError("Moondream вернула некорректный JSON.")
            parsed = json.loads(match.group(0))
            print("[Команды] Классификация через резервную Moondream.", flush=True)
        except Exception as fallback_error:
            raise RuntimeError("Groq: %s; Moondream: %s" % (primary_error, fallback_error)) from fallback_error
    action = parsed.get("action", "unknown")
    if action not in ACTIONS: action = "unknown"
    try: confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError): confidence = 0.0
    raw = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else parsed.get("arguments")
    if not isinstance(raw, dict):
        raw = {}
    safe = {
        key: value for key, value in raw.items()
        if key in (
            "attach_copied_files", "recipient_name", "reminder_text", "note_text",
            "item_text", "query", "question", "app", "app_name", "folder",
            "export_format",
        ) and isinstance(value, (str, bool))
    }
    return {
        "schema_version": 1,
        "kind": parsed.get("kind"),
        "action": action,
        "goal": parsed.get("goal", ""),
        "target": parsed.get("target") if isinstance(parsed.get("target"), dict) else {},
        "source": parsed.get("source") if isinstance(parsed.get("source"), dict) else {},
        "method": parsed.get("method", ""),
        "parameters": safe,
        "confidence": confidence,
        "clarification": parsed.get("clarification", ""),
        "response": parsed.get("response", ""),
        "arguments": safe,
    }

def understand_command(user_text: str) -> dict:
    """Return a versioned intent envelope for the execution receiver.

    The ASR transcript, semantic interpretation, and local execution are separate
    stages. Legacy fast paths are adapted to the same contract so the receiver
    never has to guess where an action applies or which data it consumes.
    """
    raw = _understand_command_legacy(user_text)
    if not isinstance(raw, dict):
        raw = {"action": "unknown", "confidence": 0.0, "arguments": {}}

    action = str(raw.get("action") or "unknown")
    args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
    params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else args
    target = raw.get("target") if isinstance(raw.get("target"), dict) else {}
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}

    # Keep only known, primitive execution parameters; no model-generated code
    # or arbitrary function names can reach the Windows action layer.
    allowed = {
        "attach_copied_files", "recipient_name", "reminder_text", "note_text",
        "item_text", "query", "question", "app", "app_name", "folder",
        "export_format",
    }
    safe = {
        key: value for key, value in params.items()
        if key in allowed and isinstance(value, (str, bool))
    }

    if action == "paste_clipboard_to_application":
        source.setdefault("type", "clipboard")
        target.setdefault("type", "application")
        target.setdefault("name", safe.get("app_name", ""))
        target.setdefault("location", "")
        raw.setdefault("goal", "Перенести содержимое буфера обмена в приложение")
        raw.setdefault("method", "Открыть целевое приложение и вставить содержимое буфера")
    elif action == "save_note":
        source.setdefault("type", "clipboard")
        target.setdefault("type", "list")
        target.setdefault("name", "заметки")
        target.setdefault("location", "")
    elif action == "add_note":
        source.setdefault("type", "spoken_text")
        target.setdefault("type", "list")
        target.setdefault("name", "заметки и дела")
        target.setdefault("location", "")
    elif action in ("open_application", "open_installed_application"):
        target.setdefault("type", "application")
        target.setdefault("name", safe.get("app_name") or safe.get("app", ""))
        target.setdefault("location", "")
    elif action in ("search_files", "search_web"):
        target.setdefault("type", "filesystem" if action == "search_files" else "website")
        target.setdefault("name", safe.get("query", ""))
        target.setdefault("location", "")

    kind = raw.get("kind")
    if kind not in ("execute", "respond", "clarify"):
        kind = "respond" if action in ("ai_chat", "camera_question") else (
            "clarify" if action == "unknown" else "execute"
        )
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    goal = str(raw.get("goal") or ACTIONS.get(action, ""))
    method = str(raw.get("method") or "")
    clarification = str(raw.get("clarification") or "")
    response = str(raw.get("response") or "")
    if kind == "clarify" and not clarification:
        clarification = response or "Уточни, пожалуйста, что именно нужно сделать и где."
    if kind == "respond" and not safe.get("question"):
        safe["question"] = user_text.strip()

    return {
        "schema_version": 1,
        "kind": kind,
        "action": action,
        "goal": goal,
        "target": {
            "type": target.get("type", "other"),
            "name": str(target.get("name") or ""),
            "location": str(target.get("location") or ""),
        },
        "source": {
            "type": source.get("type", "none"),
            "name": str(source.get("name") or ""),
        },
        "method": method,
        "parameters": safe,
        "confidence": confidence,
        "clarification": clarification,
        "response": response,
        # Compatibility adapter for the current receiver while it migrates
        # to the versioned contract.
        "arguments": safe,
    }

