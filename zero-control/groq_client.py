"""Shared OpenAI-compatible client for Groq chat completions."""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"


def chat(messages, temperature=0.2, max_tokens=1200, model=None, timeout=90,
         response_format=None):
    """Call Groq Cloud using its OpenAI-compatible chat-completions API."""
    from agent_core import get_groq_api_key, load_settings

    key = os.getenv("GROQ_API_KEY", "").strip() or get_groq_api_key()
    if not key:
        raise RuntimeError("Не задан API-ключ Groq. Добавь его в настройках Zero Control.")

    settings = load_settings()
    selected_model = str(
        model or os.getenv("GROQ_MODEL", "").strip() or settings.get("groq_model", DEFAULT_MODEL)
    ).strip()
    if not selected_model:
        raise RuntimeError("Не выбрана модель Groq.")

    # Groq пометил max_tokens устаревшим в пользу max_completion_tokens. Для GPT-OSS
    # отдельно ограничиваем reasoning, чтобы короткая классификация
    # не расходовала весь бюджет генерации на внутренние рассуждения.
    payload = {
        "model": selected_model,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "messages": messages,
    }
    if selected_model.startswith(("openai/gpt-oss-20b", "openai/gpt-oss-120b")):
        payload["reasoning_effort"] = "low"
        payload["include_reasoning"] = False
    if response_format is not None:
        payload["response_format"] = response_format

    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "ZeroControl/1.0 (Groq API client)"}, method="POST")
    # Кратковременные TLS EOF иногда возникают на сетевом маршруте до Groq.
    # Повторяем только такие сбои; HTTP-ошибки и прочие причины не маскируем.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError("Groq HTTP %s: %s" % (exc.code, detail)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            transient_tls_eof = (
                isinstance(reason, (ssl.SSLError, ConnectionError))
                and ("EOF" in str(reason).upper() or "SSL" in str(reason).upper())
            ) or "UNEXPECTED_EOF_WHILE_READING" in str(exc).upper()
            if transient_tls_eof and attempt < 2:
                print("[Groq] Временный TLS-сбой; повтор запроса %s/3." % (attempt + 2), flush=True)
                time.sleep(attempt + 1)
                continue
            raise RuntimeError("Groq недоступен: %s" % exc) from exc

    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "\n".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    answer = str(content or "").strip()
    if not answer:
        usage = data.get("usage") or {}
        diagnostic = {
            "model": data.get("model") or selected_model,
            "finish_reason": choice.get("finish_reason"),
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "message_fields": sorted(message.keys()),
        }
        refusal = message.get("refusal")
        if refusal:
            diagnostic["refusal"] = str(refusal)[:300]
        raise RuntimeError(
            "Groq вернул пустой текст; диагностика: "
            + json.dumps(diagnostic, ensure_ascii=False)
        )
    return answer
