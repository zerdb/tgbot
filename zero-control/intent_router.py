"""Groq semantic intent classification; execution stays in local Python."""
from __future__ import annotations
import json, re
ACTIONS = {
 "add_contact": "Добавить нового человека в локальную адресную книгу контактов и открыть пустую карточку.",
 "open_contacts": "Открыть общую адресную книгу контактов.",
 "open_assistant_settings": "Открыть настройки Zero Control.",
 "read_unread_mail": "Прочитать и кратко пересказать непрочитанные письма через IMAP и ИИ.",
 "ai_chat": "Ответить на вопрос пользователя через подключённую языковую модель; question — полный вопрос.",
 "email_compose": "Подготовить письмо; если просят отправить/прикрепить файлы, attach_copied_files=true. Если назван получатель, передай его имя в recipient_name. Не выбирай clarify только из-за отсутствия темы или текста письма: открой редактор. Например, «Отправь на почту Мазарову» — email_compose с recipient_name=«Мазарову»; «Отправь на почту файлы Шамилю» — email_compose с recipient_name=«Шамилю» и attach_copied_files=true.",
 "camera_question": "Получить свежий кадр камеры и ответить на вопрос пользователя по изображению; question — вопрос.",
 "inspect_camera_image": "Проверить свежий кадр камеры на наличие белой Лады Нивы; использовать только если пользователь прямо просит проверить наличие этой машины.",
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
 "inspect_screen": "Сделать свежий снимок экрана и открыть сохранённое изображение в стандартном просмотрщике Windows.",
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
Все параметры выполнения передавай только в объекте parameters. Допустимые ключи параметров: attach_copied_files (boolean), recipient_name (string), reminder_text (string), note_text (string), item_text (string), query (string), question (string), app (string), app_name (string), folder (string), export_format (string).
Не выдумывай отсутствующие сведения. Если пользователь просит вставить/перенести/поместить содержимое буфера, source.type=clipboard; target должен указывать приложение или место назначения, а method описывает открытие цели и вставку. Не выбирай приложение по умолчанию, если из контекста его нельзя надёжно понять: задай уточняющий вопрос (kind=clarify). Если цель явно указана — используй её независимо от формулировки глагола.
Если пользователь хочет сохранить содержимое буфера как заметку, это save_note, source.type=clipboard, target.type=list, target.name="заметки".
Если пользователь хочет сохранить произнесённый текст как заметку — add_note, source.type=spoken_text.
Если пользователь хочет задать вопрос, получить совет, объяснение или справку, выбери ai_chat и kind=respond; question должен содержать полный вопрос.
Если пользователь просит отправить, переслать или послать файлы/документы конкретному человеку, используй email_compose, даже если он не произносит слова «почта», «email» или «письмо»: в Zero Control это текущий способ отправки. Имя адресата укажи в parameters.recipient_name, сохраняя форму из речи; attach_copied_files=true. Если человек назван в target.name, перенеси его туда. Не спрашивай способ отправки, если адресат — человек. Не отправляй письмо автоматически: открой редактор для проверки пользователем.
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
    # «файлы/документы» — тип объекта, а не часть имени; убираем только в начале запроса.
    query = re.sub(r"^(?:мне\s+)?(?:файл\w*|документ\w*)\s+", "", query, flags=re.IGNORECASE)
    query = re.sub(r"^(?:с\s+)?(?:названием|именем)\s+", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\b(?:пдф|пфд|pdf)\b", ".pdf", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" .,!?:;")
    query = re.sub(r"\bдве\s+тысячи\s+двадцать\s+пять\b", "2025", query, flags=re.IGNORECASE)
    counts = {"один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10}
    digit_nouns = {"нул": "0", "единиц": "1", "дво": "2", "тро": "3", "четвер": "4", "пят": "5", "шестер": "6", "семер": "7", "восьмер": "8", "девят": "9"}
    for count_word, count in counts.items():
        for stem, digit in digit_nouns.items():
            query = re.sub(r"\b" + count_word + r"\s+" + stem + r"[а-яё]*\b", digit * count, query, flags=re.IGNORECASE)
    return query.strip()




def _parse_intent_json(content: str) -> dict:
    """Extract the first complete JSON object, tolerating fences and surrounding text."""
    text = str(content or "").strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    preview = re.sub(r"\s+", " ", text)[:240]
    raise RuntimeError("Модель не вернула корректный JSON-объект. Ответ: %s" % preview)


def _classify_semantically(user_text: str) -> dict:
    """Interpret the complete ASR transcript using the structured intent contract."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text[:4000]},
    ]
    provider = "groq"
    try:
        from groq_client import chat
        content = chat(messages, temperature=0, max_tokens=800, response_format={"type": "json_object"})
        print("[Команды] Семантическая классификация через Groq.", flush=True)
    except Exception as primary_error:
        print("[Команды] Groq недоступна (%s). Пробую Moondream." % primary_error, flush=True)
        try:
            from moondream_client import chat as moondream_chat
            provider = "moondream"
            content = moondream_chat(messages, temperature=0, max_tokens=800)
            print("[Команды] Семантическая классификация через Moondream.", flush=True)
        except Exception as fallback_error:
            raise RuntimeError("Groq: %s; Moondream: %s" % (primary_error, fallback_error)) from fallback_error

    parsed = _parse_intent_json(content)
    action = parsed.get("action", "unknown")
    if action not in ACTIONS:
        action = "unknown"
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    raw = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    allowed = {
        "attach_copied_files", "recipient_name", "reminder_text", "note_text",
        "item_text", "query", "question", "app", "app_name", "folder",
        "export_format",
    }
    safe = {
        key: value for key, value in raw.items()
        if key in allowed and isinstance(value, (str, bool))
    }
    result = {
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
    }
    result["_semantic_provider"] = provider
    return result


def _implicit_file_email_intent(user_text: str, semantic: dict | None = None) -> dict | None:
    """Route file transfers addressed to a person through the current email workflow."""
    normalized = re.sub(r"\\s+", " ", (user_text or "").lower().replace("ё", "е")).strip()
    if not re.search(r"\\b(отправ\\w*|перешл\\w*|пошл\\w*|передай|передать)\\b", normalized):
        return None
    if not re.search(r"\\b(файл\\w*|документ\\w*|вложен\\w*)\\b", normalized):
        return None

    semantic = semantic if isinstance(semantic, dict) else {}
    target = semantic.get("target") if isinstance(semantic.get("target"), dict) else {}
    params = semantic.get("parameters") if isinstance(semantic.get("parameters"), dict) else {}
    recipient = str(params.get("recipient_name") or "").strip()
    if not recipient and str(target.get("type") or "").lower() == "person":
        recipient = str(target.get("name") or "").strip()

    # Local fallback for a dative recipient when the semantic model is unavailable.
    if not recipient:
        patterns = (
            r"\\b(?:отправ\\w*|перешл\\w*|пошл\\w*|передай|передать)\\s+(?:мне\\s+)?(?:эти\\s+)?файл\\w*\\s+(.+)$",
            r"\\b(?:отправ\\w*|перешл\\w*|пошл\\w*|передай|передать)\\s+(.+?)\\s+(?:эти\\s+)?файл\\w*\\b",
        )
        for pattern in patterns:
            match = re.search(pattern, user_text or "", re.IGNORECASE)
            if not match:
                continue
            candidate = re.sub(
                r"\\b(?:мне|пожалуйста|срочно|эти|этих|файлы?|документы?|вложения?|по\\s+почте|на\\s+почту|email)\\b",
                " ", match.group(1), flags=re.IGNORECASE,
            )
            candidate = re.sub(r"\\s+", " ", candidate).strip(" .,!?:;«»\\\"")
            # Dative endings cover common spoken recipient forms without guessing folders or paths.
            if candidate and re.search(r"(?:у|ю|е|и|ам|ям|ом|ем|ой|ей)$", candidate.lower().replace("ё", "е")):
                recipient = candidate
                break

    if not recipient and str(target.get("type") or "").lower() != "person":
        return None
    if not recipient:
        return {
            "kind": "clarify", "action": "email_compose",
            "goal": "Отправить файлы по электронной почте",
            "target": {"type": "person", "name": "", "location": ""},
            "source": {"type": "clipboard", "name": "скопированные файлы"},
            "method": "Открыть редактор письма",
            "parameters": {"attach_copied_files": True},
            "confidence": 0.9,
            "clarification": "Кому отправить файлы?",
            "response": "",
        }

    return {
        "kind": "execute", "action": "email_compose",
        "goal": "Отправить файлы человеку по электронной почте",
        "target": {"type": "person", "name": recipient, "location": ""},
        "source": {"type": "clipboard", "name": "скопированные файлы"},
        "method": "Открыть редактор письма с файлами во вложениях",
        "parameters": {"recipient_name": recipient, "attach_copied_files": True},
        "confidence": max(0.9, float(semantic.get("confidence", 0.0) or 0.0)),
        "clarification": "", "response": "",
    }


def _understand_command(user_text: str) -> dict:
    """Use deterministic local rules before calling a semantic model."""
    # Сначала проверяем точные фразы, которые пользователь сам подтвердил
    # в настройках. Это обычные данные, не исполняемый код и не regex.
    try:
        from local_intents import match_local_intent
        learned = match_local_intent(user_text)
        if learned:
            print("[Команды] Пользовательское локальное правило: %s." % learned.get("action"), flush=True)
            return learned
    except Exception as exc:
        print("[Команды] Пользовательские правила недоступны: %s" % exc, flush=True)

    # Запуск встроенных приложений Windows не требует семантической модели:
    # точная короткая команда сразу передаётся локальному диспетчеру.
    normalized = re.sub(r"\s+", " ", (user_text or "").lower().replace("ё", "е")).strip(" .,!?:;")
    quick_app_match = re.fullmatch(
        r"(?:пожалуйста\s+)?(?:открой|открыть|запусти|запустить|включи|включить)\s+(?:мне\s+)?(блокнот|notepad|калькулятор|calculator)(?:\s+пожалуйста)?",
        normalized,
    )
    if quick_app_match:
        app_name = quick_app_match.group(1)
        app = "notepad" if app_name in ("блокнот", "notepad") else "calculator"
        print("[Команды] Локальный быстрый запуск приложения: %s." % app, flush=True)
        return {"action": "open_application", "confidence": 1.0, "parameters": {"app": app}}

    # Сначала пробуем локальный каталог действий. Обычные команды Windows и
    # запуск приложений не должны ждать сеть или расходовать квоту языковой модели.
    # Семантический слой оставляем для запросов, где важны контекст и извлечение
    # сложных параметров (письма, заметки, напоминания и т.п.).
    local_intent = _understand_command_rules(user_text)
    local_action = local_intent.get("action", "unknown")
    local_first_actions = {
        "inspect_screen",
        "open_settings",
        "open_assistant_settings",
        "open_folder",
        "add_contact",
        "open_contacts",
        "organize_folder",
        "open_reminders",
        "open_mail_client",
        "email_compose",
        "open_application",
        "open_installed_application",
        "open_downloads",
        "open_recycle_bin",
        "empty_recycle_bin",
        "lock_computer",
        "reboot_computer",
        "screenshot",
        "search_files",
        "search_web",
        "camera_question",
        "reminder",
        "add_note",
        "complete_item",
        "save_note",
        "clipboard_to_excel",
        "read_unread_mail",
    }
    if local_action in local_first_actions:
        print("[Команды] Локальная маршрутизация: %s." % local_action, flush=True)
        return local_intent

    try:
        semantic = _classify_semantically(user_text)
        implicit_email = _implicit_file_email_intent(user_text, semantic)
        if implicit_email:
            return implicit_email
        if semantic.get("kind") == "clarify":
            # Явная просьба отправить письмо — команда открыть редактор,
            # даже если модель не смогла извлечь адресата. Имя из фразы
            # передаём форме, которая сопоставит его с адресной книгой.
            target = semantic.get("target") if isinstance(semantic.get("target"), dict) else {}
            source = semantic.get("source") if isinstance(semantic.get("source"), dict) else {}
            normalized = re.sub(r"\s+", " ", (user_text or "").lower().replace("ё", "е")).strip()
            email_request = bool(
                re.search(r"\b(почт\w*|email|емейл)\b", normalized)
                and re.search(r"\b(отправ\w*|перешл\w*|пошл\w*)\b", normalized)
            )
            recipient = str(target.get("name") or "").strip()
            if not recipient:
                after_mail = re.search(r"\b(?:почту|почте|email|емейл)\s+(.+)$", user_text or "", re.IGNORECASE)
                before_mail = re.search(
                    r"\b(?:отправь|отправить|перешли|переслать|пошли|послать)\s+(.+?)\s+(?:на\s+)?(?:почту|почте|email|емейл)\b",
                    user_text or "", re.IGNORECASE,
                )
                candidate = after_mail.group(1) if after_mail else before_mail.group(1) if before_mail else ""
                candidate = re.sub(
                    r"\b(?:файл\w*|документ\w*|вложен\w*|мне|пожалуйста|срочно)\b",
                    " ", candidate, flags=re.IGNORECASE,
                )
                recipient = re.sub(r"\s+", " ", candidate).strip(" .,!?:;«»\"")
            if email_request:
                attach_files = (
                    source.get("type") == "clipboard"
                    or bool(re.search(r"\b(файл\w*|вложен\w*|буфер\w*|документ\w*)\b", normalized))
                )
                semantic["kind"] = "execute"
                semantic["action"] = "email_compose"
                semantic["parameters"] = {
                    "recipient_name": recipient,
                    "attach_copied_files": attach_files,
                }
                semantic["clarification"] = ""
                semantic["confidence"] = max(float(semantic.get("confidence", 0.0) or 0.0), 0.75)
                return semantic
            return semantic
        if semantic.get("action") != "unknown" and float(semantic.get("confidence", 0)) >= 0.55:
            return semantic
        # Даже неуверенный результат ИИ сохраняем для ручного разбора в настройках.
        try:
            from local_intents import record_intent
            record_intent(user_text, semantic, str(semantic.get("_semantic_provider") or "ai"))
        except Exception as log_error:
            print("[Намерения] Не удалось сохранить результат классификации: %s" % log_error, flush=True)
        print("[Команды] Модель не определила намерение уверенно; применяю локальный fallback.", flush=True)
    except Exception as exc:
        print("[Команды] Семантический слой недоступен; применяю локальный fallback: %s" % exc, flush=True)
    return _understand_command_rules(user_text)


def _understand_command_rules(user_text: str) -> dict:
    normalized = re.sub(r"\s+", " ", (user_text or "").lower().replace("ё", "е")).strip(" .,!?:;")
    # Убираем речевые вводные и нейтральный контекст, не меняющие намерение.
    normalized = re.sub(
        r"^(?:(?:пожалуйста|слушай|будь доб(?:р|ра))\s*[,!]?\s*)+",
        "",
        normalized,
    )
    normalized = re.sub(r"^мне нужно\s*,?\s*(?:чтобы ты\s+)?", "", normalized)
    normalized = re.sub(r"[,!]?\s+пожалуйста$", "", normalized)
    normalized = re.sub(r"\s+(?:на компьютере|на пк)$", "", normalized).strip(" .,!?:;")

    # Снимок текущего экрана — локальная команда. Учитываем варианты ASR:
    # «скрин», «скриншот», «снепшот», «фото/снимок монитора» и разные порядки слов.
    screenshot_terms = r"\b(скриншот\w*|скрин\w*|снепшот\w*|snapshot\w*|снимок\w*|фото\w*|фотографию|изображение)\b"
    screen_terms = r"\b(экран\w*|монитор\w*|диспле\w*)\b"
    screenshot_request = bool(
        re.search(screenshot_terms, normalized)
        and (
            re.search(screen_terms, normalized)
            or re.search(r"\b(сделай|сделать|создай|создать|сними|снять|получи|получить|нужен|нужна|нужно|покажи|показать)\b", normalized)
        )
    )
    screen_inspection_request = bool(
        re.search(r"\b(что|посмотри|посмотреть|прочитай|прочитать|опиши|увидь|видишь|покажи|показать)\b.*\b(на экране|экран|монитор|дисплей)", normalized)
        or normalized in ("что у меня на экране", "что видно на экране", "посмотри на экран", "покажи экран", "покажи монитор")
    )
    if screenshot_request or screen_inspection_request:
        return {"action": "inspect_screen", "confidence": 1.0, "parameters": {}}

    # Дополнительные разговорные варианты уже поддерживаемых действий.
    # Это небольшой словарь правил, не отдельная ML-модель и не тяжёлая зависимость.
    action_verbs = r"\b(открой\w*|открыть|покажи\w*|показать|зайди\w*|перейди\w*|запусти\w*|запустить|включи\w*|включить)\b"
    if re.search(r"\b(параметр\w*|настройк\w*)\b", normalized) and re.search(action_verbs, normalized):
        if re.search(r"\b(windows|систем\w*|компьютер\w*)\b", normalized):
            return {"action": "open_settings", "confidence": 1.0, "parameters": {}}
        return {"action": "open_assistant_settings", "confidence": 1.0, "parameters": {}}

    # Частые варианты открытия стандартных разделов Windows.
    if re.search(action_verbs, normalized) and re.search(r"\b(загрузк\w*|скачанн\w* файл\w*|downloads)\b", normalized):
        return {"action": "open_downloads", "confidence": 1.0, "parameters": {}}
    if re.search(action_verbs, normalized) and re.search(r"\b(корзин\w*|recycle bin)\b", normalized):
        return {"action": "open_recycle_bin", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(очист\w*|опустош\w*|освобод\w*)\b", normalized) and re.search(r"\b(корзин\w*|recycle bin)\b", normalized):
        return {"action": "empty_recycle_bin", "confidence": 1.0, "parameters": {}}

    # Управление сеансом Windows — только при явном упоминании компьютера/системы.
    if re.search(r"\b(заблокир\w*|блокир\w*)\b", normalized) and re.search(r"\b(компьютер\w*|ноутбук\w*|пк|windows|сеанс)\b", normalized):
        return {"action": "lock_computer", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(перезагруз\w*|перезапуст\w*|рестарт\w*)\b", normalized) and re.search(r"\b(компьютер\w*|ноутбук\w*|пк|windows|систем\w*)\b", normalized):
        return {"action": "reboot_computer", "confidence": 1.0, "parameters": {}}

    # Просмотр почты и подготовка письма.
    if re.search(r"\b(прочитай\w*|проверь\w*|покажи\w*|перечисли\w*|озвучь\w*|перескажи\w*)\b", normalized) and re.search(r"\b(непрочитанн\w*|нов\w* письм\w*|входящ\w*)\b", normalized):
        return {"action": "read_unread_mail", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(открой\w*|покажи\w*|зайди\w*|перейди\w*)\b", normalized) and re.search(r"\b(почт\w*|почтов\w* клиент\w*|входящ\w*|ящик\w*)\b", normalized):
        return {"action": "open_mail_client", "confidence": 1.0, "parameters": {}}

    # Адресная книга: различаем открыть список и добавить новую карточку.
    if re.search(r"\b(открой\w*|покажи\w*|выведи\w*|просмотр\w*)\b", normalized) and re.search(r"\b(контакт\w*|адресн\w* книг\w*|телефонн\w* книг\w*)\b", normalized):
        return {"action": "open_contacts", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(добав\w*|создай\w*|запиш\w*|внес\w*)\b", normalized) and re.search(r"\b(контакт\w*|адресн\w* книг\w*)\b", normalized):
        return {"action": "add_contact", "confidence": 1.0, "parameters": {}}

    # Разделяем системные настройки Windows и настройки Zero Control.
    settings_request = bool(re.search(r"\b(настройк\w*|параметр\w*)\b", normalized))
    if settings_request and re.search(r"\b(windows|систем\w*|компьютер\w*)\b", normalized):
        return {"action": "open_settings", "confidence": 1.0, "parameters": {}}
    if settings_request and re.search(r"\b(zero\s*control|помощник\w*|ассистент\w*)\b", normalized):
        return {"action": "open_assistant_settings", "confidence": 1.0, "parameters": {}}

    # Управление списком дел: формулировки «поставь/создай/добавь напоминание».
    if re.search(r"\b(напомн\w*|создай\w*|добавь\w*|поставь\w*|установи\w*)\b", normalized) and re.search(r"\b(напоминан\w*|напомни\w*)\b", normalized):
        return {"action": "reminder", "confidence": 1.0, "parameters": {"reminder_text": user_text.strip()}}
    if re.search(r"\b(открой\w*|покажи\w*|выведи\w*|отобрази\w*)\b", normalized) and re.search(r"\b(список дел|напоминан\w*|заметк\w*|задач\w*)\b", normalized):
        return {"action": "open_reminders", "confidence": 1.0, "parameters": {}}

    # Буфер обмена проверяем раньше общей конструкции «... как заметку».
    if re.search(r"\b(сохрани|сохранить|запиши|записать)\b", normalized) and re.search(r"\b(буфер обмена|содержимое буфера)\b", normalized) and re.search(r"\b(заметк\w*)\b", normalized):
        return {"action": "save_note", "confidence": 1.0, "parameters": {}}

    # Заметки из произнесённого текста.
    spoken_note = re.search(r"\b(запомни|запиши|сохрани|добавь|создай)\b\s+(.+?)\s+(?:как заметку|в заметки|в виде заметки)$", normalized)
    if spoken_note:
        note_text = spoken_note.group(2).strip(" .,!?:;")
        if note_text:
            return {"action": "add_note", "confidence": 1.0, "parameters": {"note_text": note_text}}

    # Снимок/скриншот без обязательного упоминания слова «экран».
    if re.search(r"\b(сделай|сделать|создай|создать|сними|снять|получи|получить|нужен|нужна|нужно)\b", normalized) and re.search(r"\b(скриншот\w*|скрин\w*|снепшот\w*|snapshot\w*|снимок экрана)\b", normalized):
        return {"action": "inspect_screen", "confidence": 1.0, "parameters": {}}

    # Смысловые команды с буфером определяет общий классификатор по всей фразе;\n    # не перехватываем их отдельными regex-эвристиками.\n\n    # Разделяем настройки Windows и настройки самого помощника.
    if re.search(r"\b(настройки windows|параметры windows|системные настройки|параметры системы)\b", normalized):
        return {"action": "open_settings", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(открой|открыть|покажи|показать|зайди в|перейди в)\b.*\b(настройк)", normalized) or normalized in ("настройки", "настройки помощника"):
        return {"action": "open_assistant_settings", "confidence": 1.0, "parameters": {}}

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
            return {"action": "open_folder", "confidence": 1.0, "parameters": {"folder": folder_name}}

    # Простые команды адресной книги обрабатываем локально: они не должны
    # зависеть от доступности Groq или точности ответа классификатора.
    if re.search(r"\b(добавь|добавить|запиши|записать|сохрани|сохранить)\b.*\b(в контакты|контакт|адресную книгу)\b|\b(добавь|добавить)\s+в\s+контакты\b", normalized):
        return {"action": "add_contact", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(открой|открыть|покажи|показать|посмотри|просмотреть)\b.*\b(контакты|адресную книгу)\b", normalized):
        return {"action": "open_contacts", "confidence": 1.0, "parameters": {}}
    # Локальная маршрутизация поддерживаемых команд: обычные действия не зависят от квоты Groq.
    if re.search(r"\b(разбери|разобрать|рассортируй|отсортируй|организуй)\b.*\b(папк|файл|документ)", normalized):
        return {"action": "organize_folder", "confidence": 1.0, "parameters": {}}

    # Голосовое управление общей системой заметок и дел.
    done_match = re.search(
        r"\b(отметь|пометь|закрой)\b\s+(.+?)\s+"
        r"(?:выполненным|выполненной|готовым|готовой|сделанным|сделанной|завершенным|завершенной)$",
        normalized,
    )
    if done_match:
        return {"action": "complete_item", "confidence": 1.0, "parameters": {"item_text": done_match.group(2).strip()}}
    note_match = re.match(r"^(?:запомни|сохрани заметку|добавь заметку|добавь запись)\s+(.+)$", normalized)
    if note_match:
        return {"action": "add_note", "confidence": 1.0, "parameters": {"note_text": note_match.group(1).strip()}}
    # Открытие раздела напоминаний и создание нового напоминания — разные намерения.
    if re.search(r"\b(открой|покажи|открыть|посмотреть)\b.*\b(напоминан|заметк|дела|задач)", normalized):
        return {"action": "open_reminders", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(напомни|напомнить|создай напоминание|добавь напоминание)\b", normalized):
        return {"action": "reminder", "confidence": 1.0, "parameters": {"reminder_text": user_text.strip()}}

    # Почта: создание/отправка письма открывает форму; само отправление только после кнопки пользователя.
    if re.search(r"\b(отправь|отправить|перешли|переслать)\b.*\b(почт\w*|письм\w*|email|емейл)", normalized):
        attach = bool(re.search(r"\b(файл|файлы|документ|документы|вложени)", normalized))
        recipient_name = ""
        # Получатель может стоять как после слова «почту», так и перед ним:
        # «отправь на почту Шамилю» / «отправь Шамилю на почту».
        after_mail = re.search(r"\b(?:почту|почте|email|емейл)\s+(.+)$", user_text, re.IGNORECASE)
        before_mail = re.search(r"\b(?:отправь|отправить|перешли|переслать)\s+(.+?)\s+(?:на\s+)?(?:почту|почте|email|емейл)\b", user_text, re.IGNORECASE)
        candidate = (after_mail.group(1) if after_mail else before_mail.group(1) if before_mail else "").strip(" .,!?:;«»\"")
        candidate = re.sub(r"\b(?:мне|файлы?|документы?|вложения?|пожалуйста|срочно)\b", " ", candidate, flags=re.IGNORECASE)
        candidate = re.split(
            r"\s+\b(?:о|об|про|насчет|насчёт|на тему|по поводу)\b\s+",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        candidate = re.sub(r"\s+", " ", candidate).strip(" .,!?:;«»\\\"")
        if candidate and not re.search(r"\b(?:файл|файлы|документ|документы|вложение|вложения|письмо|письма)\b", candidate, re.IGNORECASE):
            recipient_name = candidate
        return {"action": "email_compose", "confidence": 1.0, "parameters": {"attach_copied_files": attach, "recipient_name": recipient_name}}
    compose_match = re.search(
        r"\b(?:создай|создать|напиши|написать|составь|составить)\b.*?\b(?:письмо|письмецо|email)\b\s*(.*)$",
        user_text.strip(),
        flags=re.IGNORECASE,
    )
    if compose_match:
        # Имя после слова «письмо» — адресат: «напиши письмо Шамилю».
        recipient_name = compose_match.group(1).strip(" .,!?:;«»\"")
        recipient_name = re.split(
            r"\s+\b(?:о|об|про|насчет|насчёт|на тему|по поводу)\b\s+",
            recipient_name,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        recipient_name = re.sub(r"^(?:кому|для)\s+", "", recipient_name, flags=re.IGNORECASE).strip()
        # Сохраняем полное имя адресата (имя + фамилию), не обрезая его до первого слова.
        return {
            "action": "email_compose",
            "confidence": 1.0,
            "parameters": {
                "attach_copied_files": False,
                "recipient_name": recipient_name,
            },
        }
    if re.search(r"\b(открой|открыть|покажи)\b.*\b(почту|почтовый клиент|входящие)", normalized):
        return {"action": "open_mail_client", "confidence": 1.0, "parameters": {}}

    # Локальный поиск: разговорные синонимы «отыщи/разыщи/поищи».
    search_verb = r"\b(найди\w*|найти|поищи\w*|поискать|отыщи\w*|разыщи\w*|подбери\w*)\b"
    web_scope = re.search(r"\b(в интернете|в интернет\w*|в сети|в google|через google|в браузере)\b", normalized)
    if re.search(search_verb, normalized) and web_scope:
        query = re.sub(search_verb, "", normalized, count=1).strip()
        query = re.sub(r"\b(в интернете|в интернет\w*|в сети|в google|через google|в браузере)\b", "", query).strip(" .,!?:;")
        if query:
            return {"action": "search_web", "confidence": 1.0, "parameters": {"query": query}}
    if re.search(search_verb, normalized) and re.search(r"\b(файл\w*|документ\w*|папк\w*|каталог\w*)\b", normalized):
        folder_match_local = re.search(r"\b(?:папк\w*|каталог\w*)\s+(?:с\s+названи\w*\s+)?(.+)$", user_text, re.IGNORECASE)
        if folder_match_local and re.search(r"\b(папк\w*|каталог\w*)\b", normalized):
            folder_name = folder_match_local.group(1).strip().strip(" .,!?:;«»")
            if folder_name:
                return {"action": "open_folder", "confidence": 1.0, "parameters": {"folder": folder_name}}
        query = _file_search_query(user_text)
        if query:
            return {"action": "search_files", "confidence": 1.0, "parameters": {"query": query}}

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
                return {"action": "open_application", "confidence": 1.0, "parameters": {"app": app}}

    if re.search(r"\b(открой|открыть|покажи)\b.*\b(загрузки|загруженные файлы)", normalized):
        return {"action": "open_downloads", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(открой|открыть|покажи)\b.*\b(корзину|корзина)", normalized):
        return {"action": "open_recycle_bin", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(очисти|очистить|опустоши|опустошить)\b.*\b(корзину|корзина)", normalized):
        return {"action": "empty_recycle_bin", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(заблокируй|заблокировать)\b.*\b(компьютер|ноутбук|пк)", normalized):
        return {"action": "lock_computer", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(перезагрузи|перезагрузить|перезапусти)\b.*\b(компьютер|ноутбук|пк|windows)", normalized):
        return {"action": "reboot_computer", "confidence": 1.0, "parameters": {}}
    if normalized in ("скриншот", "скриншот экрана", "снимок экрана") or re.search(r"\b(сделай|сделать|сними|снять)\b.*\b(скриншот|снимок экрана)", normalized):
        return {"action": "screenshot", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(открой|открыть)\b.*\b(настройки windows|параметры windows)", normalized):
        return {"action": "open_settings", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(сохрани|сохранить)\b.*\b(заметк)", normalized):
        return {"action": "save_note", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(создай|сделай)\b.*\b(excel|эксель|таблицу из буфера)", normalized):
        return {"action": "clipboard_to_excel", "confidence": 1.0, "parameters": {}}
    # Любое другое название приложения ищем локально в меню «Пуск», на рабочем столе
    # и среди зарегистрированных приложений Windows — без обращения к языковой модели.
    open_match = re.match(
        r"^\s*(?:открой|открыть|запусти|запустить|включи|включить)\s+(.+?)\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if open_match:
        app_name = open_match.group(1).strip().strip('"«»')
        app_name = re.sub(r"\s+(?:на компьютере|на пк|пожалуйста)$", "", app_name, flags=re.IGNORECASE).strip()
        if app_name and not re.search(
            r"\b(папк|директор|каталог|файл|документ|загрузк|корзин|настройк|параметр|контакт|почт|напоминан|заметк|дела|задач)\w*\b",
            app_name.lower().replace("ё", "е"),
        ):
            return {
                "action": "open_installed_application",
                "confidence": 1.0,
                "parameters": {"app_name": app_name},
            }

    # Явный поиск папки по названию — используем индекс каталогов, а не файлов.
    folder_query = re.search(r"\b(?:найди|поищи|найти|поискать)\b.*\bпапк\w*\s+(?:с\s+названи\w*\s+)?(.+)$", user_text, re.IGNORECASE)
    if folder_query and folder_query.group(1).strip():
        return {"action": "open_folder", "confidence": 1.0, "parameters": {"folder": folder_query.group(1).strip().strip("«»")}}
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
                    "parameters": {"query": query, "export_format": export_format},
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
            return {"action": "search_files", "confidence": 1.0, "parameters": {"query": query}}

    if re.search(r"\b(найди|поищи|найти|поискать)\b", normalized) and not re.search(r"\b(в интернете|в интернет|в сети|в google)\b", normalized):
        query = _file_search_query(user_text)
        if query:
            return {"action": "search_files", "confidence": 1.0, "parameters": {"query": query}}
    if re.search(r"\b(поищи|найди|найти)\b", normalized) and re.search(r"\b(в интернете|в интернет|в сети|в google)\b", normalized):
        query = re.sub(r"^.*?\b(?:поищи|найди|найти)\b", "", normalized).strip()
        query = re.sub(r"\b(?:в интернете|в интернет|в сети|в google)\b", "", query).strip()
        return {"action": "search_web", "confidence": 1.0, "parameters": {"query": query or user_text.strip()}}

    # Вопросы о наблюдении отправляем на анализ свежего кадра.
    camera_context = re.search(r"\b(камера|камере|камеру|видеонаблюдени|на парковке|во дворе|у ворот|в кадре|на изображении|на видео|на записи|там|здесь|тут|картинк)\b", normalized)
    camera_question = re.search(r"\b(что|кто|сколько|есть|видно|видишь|опиши|день|ночь|машин|людей|человек|сейчас)\b", normalized)
    if camera_context and camera_question:
        return {"action": "camera_question", "confidence": 1.0, "parameters": {"question": user_text.strip()}}
    if re.search(r"\b(настройки помощника|настройки zero control)\b", normalized):
        return {"action": "open_assistant_settings", "confidence": 1.0, "parameters": {}}
    if re.search(r"\b(прочитай|проверь|покажи)\b.*\b(новые|непрочитанные)\b.*\b(письма|почту)\b", normalized):
        return {"action": "read_unread_mail", "confidence": 1.0, "parameters": {}}
    if _is_natural_information_question(user_text):
        return {"action": "ai_chat", "confidence": 0.99, "parameters": {"question": user_text.strip()}}
    return {"action": "unknown", "confidence": 0.0, "parameters": {}}


def understand_command(user_text: str) -> dict:
    """Return the single versioned intent contract used by every execution path.

    Model classification and deterministic fallbacks are normalized here;
    neither may expose a second parameter format to the execution receiver.
    """
    raw = _understand_command(user_text)
    if not isinstance(raw, dict):
        raw = {"action": "unknown", "confidence": 0.0, "parameters": {}}

    action = str(raw.get("action") or "unknown")
    params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
    target = raw.get("target") if isinstance(raw.get("target"), dict) else {}
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}

    # Keep only known primitive parameters; model output never selects Python
    # functions or supplies executable code.
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
        # The semantic destination is mapped to the canonical app_name parameter
        # required by the existing Windows action implementation.
        if target.get("name") and not safe.get("app_name"):
            safe["app_name"] = str(target["name"])
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
        if target.get("name"):
            if action == "open_application":
                safe.setdefault("app", str(target["name"]))
            else:
                safe.setdefault("app_name", str(target["name"]))
    elif action == "open_folder":
        target.setdefault("type", "folder")
        target.setdefault("name", safe.get("folder", ""))
        target.setdefault("location", "")
        if target.get("name"):
            safe.setdefault("folder", str(target["name"]))
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
    # Never execute a destination-dependent operation with an invented or
    # missing target. Ask once, then let the next utterance complete the intent.
    if action == "paste_clipboard_to_application" and not safe.get("app_name"):
        kind = "clarify"
        clarification = "В какое приложение вставить содержимое буфера обмена?"
    if action == "open_installed_application" and not safe.get("app_name"):
        kind = "clarify"
        clarification = "Какое приложение нужно открыть?"
    if kind == "respond" and not safe.get("question"):
        safe["question"] = user_text.strip()

    result = {
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
    }
    provider = raw.get("_semantic_provider")
    if provider:
        try:
            from local_intents import record_intent
            record_intent(user_text, result, str(provider))
        except Exception as exc:
            print("[Намерения] Журнал недоступен: %s" % exc, flush=True)
    return result

