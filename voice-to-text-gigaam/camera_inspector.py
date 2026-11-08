"""Capture an RTSP frame and inspect it with Moondream vision."""
import os
import json
import base64
import re
import urllib.request
import urllib.error
import subprocess
from urllib.parse import quote


def _capture_camera_image() -> str:
    import cv2
    from agent_core import get_camera_password
    url = os.getenv("ZERO_CONTROL_CAMERA_RTSP_URL", os.getenv("GIGAAM_CAMERA_RTSP_URL", "")).strip()
    if not url:
        secret = get_camera_password()
        if not secret:
            raise RuntimeError("Сначала сохрани пароль камеры в настройках.")
        url = "rtsp://admin:" + quote(secret, safe="") + "@10.1.5.152:554"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            raise RuntimeError("Не удалось открыть RTSP-камеру.")
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Не удалось получить кадр камеры.")
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            raise RuntimeError("Не удалось подготовить снимок.")
        return base64.b64encode(jpg.tobytes()).decode("ascii")
    finally:
        cap.release()


def _ask_moondream(image_data: str, api_key: str, question: str = None, strict_answer: bool = False):
    # Для произвольных вопросов задаём модели строгий формат короткого ответа.
    prompt = question or (
        "Is a white Lada Niva (Lada 4x4) car clearly visible in this surveillance image? "
        "Answer with exactly YES or NO. Answer NO if the car is absent, unclear, too small, "
        "or you are uncertain. Do not infer from context."
    )
    if question and not strict_answer:
        # Сначала сам вопрос, затем короткие требования к ответу. Некоторые
        # версии vision-модели ошибочно копируют последнюю часть длинного промпта.
        prompt = (
            "Вопрос: " + question + "\n"
            "Рассмотри приложенное изображение, а не текст вопроса. Сначала определи, "
            "что реально видно: люди, автомобили, предметы, действия и обстановка. "
            "Затем ответь на вопрос по этим визуальным признакам. "
            "Не повторяй вопрос и не объясняй, как работают камеры. "
            "Если детали мелкие или размытые, укажи это конкретно. "
            "Пиши по-русски, 1-3 коротких предложения."
        )
    payload = {
        "model": "moondream3.1-9B-A2B",
        "image_url": "data:image/jpeg;base64," + image_data,
        "question": prompt,
        "reasoning": True,
    }
    req = urllib.request.Request(
        "https://api.moondream.ai/v1/query",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-Moondream-Auth": api_key,
            "Content-Type": "application/json",
            "User-Agent": "ZeroControl/1.0 (Windows; camera vision client)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Moondream вернул HTTP {exc.code}: {detail}") from exc
    answer = str(data.get("answer", "")).strip()
    if not answer:
        raise RuntimeError("Moondream вернул пустой ответ.")
    return answer




def inspect_camera():
    from agent_core import get_moondream_api_key
    image_data = _capture_camera_image()
    key = os.getenv("MOONDREAM_API_KEY", "").strip() or get_moondream_api_key()
    if not key:
        raise RuntimeError("Для анализа камеры нужен API-ключ Moondream. Модель Groq llama-3.3-70b-versatile не поддерживает изображения.")
    answer = _ask_moondream(image_data, key)
    first_word = re.sub(r"[^A-Z]", " ", answer.upper()).split()
    return bool(first_word and first_word[0] == "YES")


def _compact_camera_answer(answer: str) -> str:
    """Remove repeated sentences and keep spoken camera answers short."""
    answer = re.sub(r"\s+", " ", str(answer or "")).strip().strip('"“”')
    if not answer:
        return "Не удалось разобрать изображение."
    # Не показываем пользователю фрагменты служебного промпта, если модель
    # вместо анализа кадра повторила инструкции.
    leaked_prompt = (
        "максимум 1-2 предложения", "максимум 1–2 предложения",
        "вопрос пользователя:", "отвечай только по-русски",
        "не добавляй вступление", "описывай только то"
    )
    if any(marker in answer.lower() for marker in leaked_prompt):
        return "ИИ повторил инструкцию вместо анализа кадра. Повтори вопрос."
    # Частый сбой vision-модели: она повторяет вопрос, а затем сочиняет
    # текст, не связанный с изображением. Такой ответ не выдаём за анализ.
    question = getattr(_compact_camera_answer, "_question", "")
    normalized_answer = re.sub(r"[^а-яa-z0-9]+", " ", answer.lower().replace("ё", "е")).strip()
    normalized_question = re.sub(r"[^а-яa-z0-9]+", " ", question.lower().replace("ё", "е")).strip()
    if normalized_question and normalized_answer.startswith(normalized_question):
        return "ИИ повторил вопрос вместо анализа изображения. Попробуй спросить конкретнее: например, какие машины или люди видны."
    parts = re.split(r"(?<=[.!?])\s+", answer)
    unique = []
    seen = set()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        key = re.sub(r"[^а-яa-z0-9]+", "", part.lower().replace("ё", "е"))
        if key and key not in seen:
            seen.add(key)
            unique.append(part)
        if len(unique) >= 2:
            break
    result = " ".join(unique) or answer
    words = result.split()
    if len(words) > 25:
        result = " ".join(words[:25]).rstrip(" ,;:") + "."
    if len(result) > 240:
        result = result[:237].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return result


def _is_white_car_presence_question(question: str) -> bool:
    q = re.sub(r"\s+", " ", (question or "").lower().replace("ё", "е")).strip()
    asks_presence = bool(re.search(r"\b(есть|видно|видишь|присутствует|находится)\b", q))
    mentions_white = bool(re.search(r"\b(бел(ая|ую|ого|ый|ое)?|светл(ая|ую|ый|ое)?)\b", q))
    mentions_car = bool(re.search(r"\b(машин(а|у|ы|е)?|автомобил(ь|я|и)?|нива|лада)\b", q))
    return asks_presence and mentions_white and mentions_car


def _yes_no_result(answer: str) -> str:
    value = (answer or "").strip().lower()
    first = re.sub(r"[^a-zа-я]+", " ", value).strip().split()
    if not first:
        return "Не удалось определить по кадру."
    if first[0] in ("yes", "да", "true", "present"):
        return "Да, белая машина видна на кадре."
    if first[0] in ("no", "нет", "false", "absent"):
        return "Нет, белой машины на кадре не видно."
    # При неоднозначном ответе не превращаем предположение в факт.
    if any(x in value for x in ("uncertain", "не уверен", "неразлич", "не могу определить")):
        return "Не могу уверенно определить по этому кадру."
    raise RuntimeError("Модель не дала однозначный ответ да/нет: " + value[:240])


def inspect_camera_question(question: str) -> str:
    """Ask Moondream about a fresh camera frame; Groq's selected model is text-only."""
    from agent_core import get_moondream_api_key
    question = (question or "").strip() or "Опиши, что видно на изображении."
    image_data = _capture_camera_image()
    key = os.getenv("MOONDREAM_API_KEY", "").strip() or get_moondream_api_key()
    if not key:
        raise RuntimeError("Для анализа камеры нужен API-ключ Moondream. Groq llama-3.3-70b-versatile не принимает изображения.")
    if _is_white_car_presence_question(question):
        prompt = (
            "Is a white car clearly visible in this surveillance image? "
            "Answer with exactly YES or NO. Answer NO if no white car is visible "
            "or if you are uncertain. Do not describe the question or guess."
        )
        return _yes_no_result(_ask_moondream(image_data, key, prompt, strict_answer=True))
    answer = _ask_moondream(image_data, key, question)
    _compact_camera_answer._question = question
    try:
        compact = _compact_camera_answer(answer)
    finally:
        _compact_camera_answer._question = ""
    if compact.startswith("ИИ повторил"):
        raise RuntimeError(compact)
    return compact

def speak(text):
    encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
    script = "$t=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + encoded + "'));Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.Rate=1;$s.Speak($t);$s.Dispose()"
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
