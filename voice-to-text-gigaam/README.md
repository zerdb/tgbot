# Voice to Text — GigaAM

Push-to-talk voice typing for your desktop. Hold **Right Ctrl** to record; release it to transcribe with [GigaAM](https://github.com/salute-developers/GigaAM) and paste the recognized text at the cursor.

> This folder is independent of the other projects in the `tgbot` repository. It does not use Vosk.

## Requirements

- Python 3.10+
- A working microphone
- [FFmpeg](https://ffmpeg.org/) installed and available on `PATH`
- Windows is the primary target (the `keyboard` package may require elevated permissions on some systems)

## Installation

Install the official GigaAM package first:

```bash
git clone https://github.com/salute-developers/GigaAM.git
cd GigaAM
pip install -e ".[torch]"
```

Then install this project's dependencies:

```bash
cd ../tgbot/voice-to-text-gigaam
python -m pip install -r requirements.txt
```

## Run

```bash
python main.py
```

1. Wait until the GigaAM model is loaded.
2. Hold **Right Ctrl** and speak.
3. Release **Right Ctrl**. The recognized text is copied to the clipboard and pasted into the active window.
4. Press **Esc** to exit.

The default model is `e2e_rnnt`. To choose another supported GigaAM model:

**Windows PowerShell**
```powershell
$env:GIGAAM_MODEL="v3_e2e_rnnt"
python main.py
```

**Linux/macOS**
```bash
GIGAAM_MODEL=v3_e2e_rnnt python main.py
```

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GIGAAM_MODEL` | `e2e_rnnt` | Model name passed to `gigaam.load_model()` |
| `PUSH_TO_TALK_KEY` | `right ctrl` | Key held while recording |
| `SAMPLE_RATE` | `16000` | Microphone sample rate |

## Notes

- The model weights are downloaded by GigaAM when the model is first loaded; they are not stored in this repository.
- Audio is written to a temporary WAV file for inference and deleted afterward.
- The default GigaAM `.transcribe()` interface is intended for short clips. For longer recordings, use the long-form API and its optional dependencies as described in the official GigaAM documentation.
- Make sure the target text field is focused before releasing the hotkey.
