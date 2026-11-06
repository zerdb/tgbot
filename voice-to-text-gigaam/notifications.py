"""Windows toast notifications and consistent Russian speech synthesis."""
from __future__ import annotations

import base64
import subprocess
from winotify import Notification, audio


def show_notification(title: str, message: str):
    toast = Notification(app_id="GigaAM Voice Assistant", title=title, msg=message, duration="long")
    toast.set_audio(audio.Default, loop=False)
    toast.show()


def speak_text(message: str):
    """Speak only with a detected male SAPI voice; never silently fall back to a female voice."""
    text = str(message or "").strip()
    if not text:
        return
    encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
    script = (
        "$ErrorActionPreference='Stop';"
        "$t=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + encoded + "'));"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$voices=@($s.GetInstalledVoices() | Where-Object {$_.Enabled});"
        "$maleRu=@($voices | Where-Object {"
        "$_.VoiceInfo.Gender -eq [System.Speech.Synthesis.VoiceGender]::Male -and "
        "$_.VoiceInfo.Culture.Name -like 'ru*'});"
        "if($maleRu.Count -gt 0){$v=$maleRu[0]}else{"
        "$male=@($voices | Where-Object {$_.VoiceInfo.Gender -eq "
        "[System.Speech.Synthesis.VoiceGender]::Male});"
        "if($male.Count -gt 0){$v=$male[0]}else{"
        "throw 'Не найден установленный мужской голос Windows. Установите мужской голос в параметрах речи Windows.'}};"
        "$s.SelectVoice($v.VoiceInfo.Name);"
        "$s.Rate=0;$s.Volume=100;$s.Speak($t);$s.Dispose()"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
