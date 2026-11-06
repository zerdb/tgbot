"""Shared client for Ollama Cloud chat and vision models."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


ENDPOINT = "https://ollama.com/v1/chat/completions"


def chat(messages, temperature=0.2, max_tokens=1200, model=None, timeout=90):
    """Call Ollama Cloud directly; no Ollama desktop app or local model is required."""
    from agent_core import get_ollama_api_key, load_settings

    key = os.getenv("OLLAMA_API_KEY", "").strip() or get_ollama_api_key()
    if not key:
        raise RuntimeError("Не задан ключ Ollama Cloud. Добавь его в настройках Zero Control.")

    settings = load_settings()
    selected_model = str(
        model or os.getenv("OLLAMA_MODEL", "").strip() or settings.get("ollama_model", "gemma4:31b")
    ).strip()
    if not selected_model:
        raise RuntimeError("Не выбрана модель Ollama Cloud.")

    payload = {
        "model": selected_model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError("Ollama Cloud HTTP %s: %s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Ollama Cloud недоступна: %s" % exc) from exc

    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    if isinstance(content, list):
        content = "\n".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("Ollama Cloud вернула пустой ответ.")
    return answer
