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
    """Speak with an installed male SAPI voice and report synthesis failures."""
    text = str(message or "").strip()
    if not text:
        return
    encoded = base64.b64encode(text.encode("utf-16le")).decode("ascii")
    script = (
        "$ErrorActionPreference='Stop';"
        "try {"
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
        "throw ('Мужской голос Windows не найден. Доступные голоса: ' + "
        "(($voices | ForEach-Object {$_.VoiceInfo.Name + ' [' + $_.VoiceInfo.Gender + ', ' + $_.VoiceInfo.Culture.Name + ']'}) -join '; '))}};"
        "$s.SelectVoice($v.VoiceInfo.Name);"
        "Write-Output ('VOICE_SELECTED=' + $v.VoiceInfo.Name);"
        "$s.Rate=0;$s.Volume=100;$s.Speak($t);$s.Dispose();"
        "} catch { [Console]::Error.WriteLine($_.Exception.ToString()); exit 1 }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "PowerShell завершился без описания ошибки").strip()
            print(f"[Озвучивание] Не удалось произнести текст: {details}", flush=True)
        else:
            selected = next(
                (line.partition("=")[2] for line in result.stdout.splitlines() if line.startswith("VOICE_SELECTED=")),
                "мужской голос Windows",
            )
            print(f"[Озвучивание] Используется: {selected}", flush=True)
    except subprocess.TimeoutExpired:
        print("[Озвучивание] Синтез речи не завершился за 45 секунд.", flush=True)
    except OSError as exc:
        print(f"[Озвучивание] Не удалось запустить Windows PowerShell: {exc}", flush=True)
