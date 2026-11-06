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
    """Speak with an installed Russian male SAPI voice when available."""
    text = str(message or "").strip()
    if not text:
        return
    encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
    script = (
        "$t=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + encoded + "'));"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$voices=@($s.GetInstalledVoices() | Where-Object {$_.Enabled});"
        "$v=$voices | Where-Object {$_.VoiceInfo.Gender -eq "
        "[System.Speech.Synthesis.VoiceGender]::Male -and $_.VoiceInfo.Culture.Name -like 'ru*'} "
        "| Select-Object -First 1;"
        "if(-not $v){$v=$voices | Where-Object {$_.VoiceInfo.Gender -eq "
        "[System.Speech.Synthesis.VoiceGender]::Male} | Select-Object -First 1};"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        "$s.Rate=0;$s.Volume=100;$s.Speak($t);$s.Dispose()"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
