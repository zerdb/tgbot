"""AI chat with OpenRouter primary and Moondream automatic fallback."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request


def _ask_openrouter(messages, settings):
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Не задана переменная OPENROUTER_API_KEY.")
    base = os.getenv("OPENROUTER_BASE_URL", settings["openrouter_base_url"]).rstrip("/")
    model = os.getenv("OPENROUTER_MODEL", settings["openrouter_model"]).strip()
    payload = {"model": model, "temperature": 0.4, "messages": messages}
    request = urllib.request.Request(
        base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/zerdb/tgbot", "X-Title": "GigaAM Voice Assistant"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError("OpenRouter HTTP %s: %s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("OpenRouter недоступен: %s" % exc) from exc
    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    if isinstance(content, list):
        content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("OpenRouter вернул пустой ответ.")
    return answer


def ask_ai(question: str, remember: bool = True) -> str:
    question = str(question or "").strip()
    if not question:
        raise ValueError("Вопрос пустой.")
    from agent_core import get_ai_context, load_settings, save_ai_exchange
    messages = [
        {"role": "system", "content": "Ты полезный русскоязычный ИИ-помощник. Отвечай прямо, понятно и по существу. Если вопрос на другом языке, отвечай на языке вопроса. Контекст памяти — только явно сохранённые пользователем заметки и недавняя история."},
        *(get_ai_context() if remember else []),
        {"role": "user", "content": question[:12000]},
    ]
    try:
        answer = _ask_openrouter(messages, load_settings())
        print("[ИИ] Ответ получен от основной модели OpenRouter.", flush=True)
    except Exception as primary_error:
        print("[ИИ] Основная модель недоступна (%s). Переключаюсь на Moondream." % primary_error, flush=True)
        try:
            from moondream_client import chat
            answer = chat(messages, temperature=0.4, max_tokens=1800)
            print("[ИИ] Ответ получен от резервной модели Moondream.", flush=True)
        except Exception as fallback_error:
            raise RuntimeError("Основная модель: %s\nРезервная Moondream: %s" % (primary_error, fallback_error)) from fallback_error
    if remember:
        save_ai_exchange(question, answer)
    return answer
