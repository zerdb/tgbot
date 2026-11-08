"""Shared Moondream chat-completions client used as the assistant fallback."""
from __future__ import annotations
import json
import urllib.error
import urllib.request

MODEL = "moondream3.1-9B-A2B"
ENDPOINT = "https://api.moondream.ai/v1/chat/completions"


def chat(messages, temperature=0.2, max_tokens=1200):
    from agent_core import get_moondream_api_key
    key = get_moondream_api_key()
    if not key:
        raise RuntimeError("Ключ Moondream не сохранён в настройках.")
    payload = {"model": MODEL, "messages": messages, "temperature": temperature,
               "max_completion_tokens": max_tokens}
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": "ZeroControl/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError("Moondream HTTP %s: %s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Moondream недоступен: %s" % exc) from exc
    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    if isinstance(content, list):
        content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("Moondream вернул пустой ответ.")
    return answer
