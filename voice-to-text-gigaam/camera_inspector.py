"""Capture an RTSP frame and inspect it with Moondream or OpenRouter."""
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
    url = os.getenv("GIGAAM_CAMERA_RTSP_URL", "").strip()
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


def _ask_moondream(image_data: str, api_key: str, question: str = None):
    prompt = question or (
        "Is a white Lada Niva (Lada 4x4) car clearly visible in this surveillance image? "
        "Answer with exactly YES or NO. Answer NO if the car is absent, unclear, too small, "
        "or you are uncertain. Do not infer from context."
    )
    payload = {
        "model": "moondream3.1-9B-A2B",
        "image_url": "data:image/jpeg;base64," + image_data,
        "question": prompt,
    }
    req = urllib.request.Request(
        "https://api.moondream.ai/v1/query",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "X-Moondream-Auth": api_key,
            "Content-Type": "application/json",
            "User-Agent": "GigaAMVoiceAssistant/1.0 (Windows; camera vision client)",
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


def _ask_openrouter(image_data: str, question: str = None):
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Не задан ключ Moondream и отсутствует OPENROUTER_API_KEY.")
    from agent_core import load_settings
    cfg = load_settings()
    base = os.getenv("OPENROUTER_BASE_URL", cfg.get("openrouter_base_url", "https://openrouter.ai/api/v1")).rstrip("/")
    model = os.getenv("OPENROUTER_MODEL", cfg.get("openrouter_model", "openrouter/free")).strip()
    prompt = question or (
        "Is a white Lada Niva car visible in this surveillance image? Do not guess. "
        "Return only JSON: {present: boolean, confidence: number, reason: string}. "
        "If uncertain, present must be false."
    )
    payload = {"model": model, "temperature": 0, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_data}},
    ]}]}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("OpenRouter вернул HTTP " + str(exc.code) + ": " + exc.read().decode(errors="replace")[:500]) from exc
    choices = data.get("choices") or []
    answer = (choices[0].get("message") or {}).get("content", "") if choices else ""
    if isinstance(answer, list):
        answer = " ".join(x.get("text", "") for x in answer if isinstance(x, dict))
    answer = str(answer or "").strip()
    if not answer:
        raise RuntimeError("OpenRouter вернул пустой ответ.")
    return answer


def inspect_camera():
    from agent_core import get_moondream_api_key
    image_data = _capture_camera_image()
    moondream_key = os.getenv("MOONDREAM_API_KEY", "").strip() or get_moondream_api_key()
    if moondream_key:
        print("[Камера] Использую Moondream для анализа снимка.", flush=True)
        answer = _ask_moondream(image_data, moondream_key)
        first_word = re.sub(r"[^A-Z]", " ", answer.upper()).split()
        return bool(first_word and first_word[0] == "YES")
    print("[Камера] Ключ Moondream не задан — использую OpenRouter.", flush=True)
    answer = _ask_openrouter(image_data)
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        raise RuntimeError("OpenRouter не вернул JSON. Нужна vision-модель.")
    return json.loads(match.group(0)).get("present") is True


def inspect_camera_question(question: str) -> str:
    """Ask a natural-language question about a fresh camera frame."""
    from agent_core import get_moondream_api_key
    question = (question or "").strip()
    if not question:
        question = "Опиши, что видно на изображении."
    image_data = _capture_camera_image()
    moondream_key = os.getenv("MOONDREAM_API_KEY", "").strip() or get_moondream_api_key()
    if moondream_key:
        print("[Камера] Отправляю вопрос по свежему кадру в Moondream.", flush=True)
        answer = _ask_moondream(image_data, moondream_key, question)
    else:
        print("[Камера] Moondream не настроен — пробую OpenRouter vision.", flush=True)
        answer = _ask_openrouter(image_data, question)
    return answer.strip()

def speak(text):
    encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
    script = "$t=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + encoded + "'));Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.Rate=-1;$s.Speak($t);$s.Dispose()"
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
