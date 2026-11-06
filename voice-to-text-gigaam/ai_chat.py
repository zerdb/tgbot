"""AI chat with Ollama Cloud primary and Moondream automatic fallback."""
from __future__ import annotations


def ask_ai(question: str, remember: bool = True) -> str:
    question = str(question or "").strip()
    if not question:
        raise ValueError("Вопрос пустой.")
    from agent_core import get_ai_context, save_ai_exchange
    messages = [
        {"role": "system", "content": "Ты полезный русскоязычный ИИ-помощник. Отвечай прямо, понятно и по существу. Если вопрос на другом языке, отвечай на языке вопроса. Контекст памяти — только явно сохранённые пользователем заметки и недавняя история."},
        *(get_ai_context() if remember else []),
        {"role": "user", "content": question[:12000]},
    ]
    try:
        from ollama_client import chat
        answer = chat(messages, temperature=0.4, max_tokens=1800)
        print("[ИИ] Ответ получен от основной модели Ollama Cloud.", flush=True)
    except Exception as primary_error:
        print("[ИИ] Ollama Cloud недоступна (%s). Переключаюсь на Moondream." % primary_error, flush=True)
        try:
            from moondream_client import chat as moondream_chat
            answer = moondream_chat(messages, temperature=0.4, max_tokens=1800)
            print("[ИИ] Ответ получен от резервной модели Moondream.", flush=True)
        except Exception as fallback_error:
            raise RuntimeError("Ollama Cloud: %s\\nРезервная Moondream: %s" % (primary_error, fallback_error)) from fallback_error
    if remember:
        save_ai_exchange(question, answer)
    return answer
