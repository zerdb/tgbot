"""Direct question-and-answer requests to the user's configured OpenRouter model."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request


def ask_ai(question: str, remember: bool = True) -> str:
    question = str(question or "").strip()
    if not question:
        raise ValueError("Вопрос пустой.")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Не задана переменная OPENROUTER_API_KEY.")
    from agent_core import get_ai_context, load_settings, save_ai_exchange
    settings = load_settings()
    base = os.getenv("OPENROUTER_BASE_URL", settings["openrouter_base_url"]).rstrip("/")
    model = os.getenv("OPENROUTER_MODEL", settings["openrouter_model"]).strip()
    messages = [
        {"role": "system", "content": "Ты полезный русскоязычный ИИ-помощник. Отвечай прямо, понятно и по существу. Если вопрос на другом языке, отвечай на языке вопроса. Контекст памяти — только явно сохранённые пользователем заметки и недавняя история."},
        *(get_ai_context() if remember else []),
        {"role": "user", "content": question[:12000]},
    ]
    payload = {"model": model, "temperature": 0.4, "messages": messages}
    request = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/zerdb/tgbot", "X-Title": "GigaAM Voice Assistant",
    }, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError("OpenRouter HTTP %s: %s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("OpenRouter недоступен: %s" % exc) from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter не вернул ответ.")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("Подключённая модель вернула пустой ответ.")
    if remember:
        save_ai_exchange(question, answer)
    return answer
