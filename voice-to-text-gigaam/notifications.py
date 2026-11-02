"""Windows toast notifications and speech synthesis."""
from __future__ import annotations

import subprocess
from winotify import Notification, audio

def show_notification(title: str, message: str):
    toast = Notification(app_id="GigaAM Voice Assistant", title=title, msg=message, duration="long")
    toast.set_audio(audio.Default, loop=False)
    toast.show()

def speak_text(message: str):
    # Windows встроенный SAPI, не требует отдельного TTS-пакета или интернета.
    escaped = message.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{escaped}')"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", script],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

