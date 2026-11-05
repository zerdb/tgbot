"""Capture one RTSP frame and ask the configured OpenRouter vision model."""
import os, json, base64, re, urllib.request, urllib.error, subprocess
from urllib.parse import quote

def inspect_camera():
    import cv2
    from agent_core import get_camera_password, load_settings
    url=os.getenv("GIGAAM_CAMERA_RTSP_URL","").strip()
    if not url:
        secret=get_camera_password()
        if not secret:
            raise RuntimeError("Сначала сохрани пароль камеры в настройках.")
        url="rtsp://admin:"+quote(secret,safe="")+"@10.1.5.152:554"
    cap=cv2.VideoCapture(url,cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened(): raise RuntimeError("Не удалось открыть RTSP-камеру.")
        ok,frame=cap.read()
        if not ok: raise RuntimeError("Не удалось получить кадр камеры.")
        ok,jpg=cv2.imencode(".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,82])
        if not ok: raise RuntimeError("Не удалось подготовить снимок.")
        image=base64.b64encode(jpg.tobytes()).decode("ascii")
    finally: cap.release()
    key=os.getenv("OPENROUTER_API_KEY","").strip()
    if not key: raise RuntimeError("Не задан OPENROUTER_API_KEY.")
    cfg=load_settings()
    base=os.getenv("OPENROUTER_BASE_URL",cfg.get("openrouter_base_url","https://openrouter.ai/api/v1")).rstrip("/")
    model=os.getenv("OPENROUTER_MODEL",cfg.get("openrouter_model","openrouter/free")).strip()
    prompt="Is a white Lada Niva car visible in this surveillance image? Do not guess. Return only JSON: {present: boolean, confidence: number, reason: string}. If uncertain, present must be false."
    payload={"model":model,"temperature":0,"messages":[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+image}}]}]}
    req=urllib.request.Request(base+"/chat/completions",data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=60) as response: data=json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Vision-модель вернула HTTP "+str(exc.code)+": "+exc.read().decode(errors="replace")[:500]) from exc
    choices=data.get("choices") or []
    answer=(choices[0].get("message") or {}).get("content","") if choices else ""
    if isinstance(answer,list): answer=" ".join(x.get("text","") for x in answer if isinstance(x,dict))
    match=re.search(r"\{.*\}",str(answer),re.S)
    if not match: raise RuntimeError("Выбранная модель не вернула JSON. Нужна модель с поддержкой изображений.")
    result=json.loads(match.group(0))
    return result.get("present") is True

def speak(text):
    import base64, subprocess
    encoded=base64.b64encode(text.encode("utf-16le")).decode("ascii")
    script="$t=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('"+encoded+"'));Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.Speak($t);$s.Dispose()"
    subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",script],check=True,timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
