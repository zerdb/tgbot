# Voice to Text — Local GigaAM-v3

Offline push-to-talk voice typing and voice commands for Windows. Hold **Right Alt + Right Shift** together to dictate text; hold **Right Ctrl** to issue a voice command. Release the key to process the recording with a locally stored GigaAM-v3 model.

**No Vosk. No API. No network access at inference time.** The model is loaded from a local directory using `local_files_only=True`.

## 1. Download the model

Download the official GigaAM-v3 end-to-end RNNT model from Hugging Face:

- [GigaAM-v3 — e2e_rnnt model files](https://huggingface.co/ai-sage/GigaAM-v3/tree/e2e_rnnt)
- [Official GigaAM project and documentation](https://github.com/salute-developers/GigaAM)

The model snapshot is about 449 MB. Download **all files** from the `e2e_rnnt` revision (including `config.json`, `modeling_gigaam.py`, `pytorch_model.bin`, and `tokenizer.model`).

The easiest way is with the Hugging Face CLI:

```powershell
py -m pip install -U huggingface_hub
hf download ai-sage/GigaAM-v3 --revision e2e_rnnt --local-dir GigaAM-v3
```

Place the resulting `GigaAM-v3` folder **next to** `voice-to-text-gigaam`, like this:

```text
tgbot/
├── GigaAM-v3/
│   ├── config.json
│   ├── modeling_gigaam.py
│   ├── pytorch_model.bin
│   └── tokenizer.model
└── voice-to-text-gigaam/
    ├── main.py
    ├── requirements.txt
    └── README.md
```

Do not put the model weights into GitHub; the model is downloaded separately.

## 2. Install dependencies

Use Python 3.10 or newer. Install FFmpeg and add it to PATH if required by your audio environment.

From the `voice-to-text-gigaam` folder:

```powershell
py -m venv .venv
.venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

PyTorch installation can differ by hardware. If you need a CUDA-enabled build, install the matching PyTorch/torchaudio wheels from the [official PyTorch selector](https://pytorch.org/get-started/locally/) instead of the CPU/default wheels.

## Local neural speech synthesis

Voice announcements use the local Piper TTS engine and the Russian **Denis (medium)** voice, not Windows SAPI voices. On the first spoken announcement, Zero Control installs the Piper Python package if needed and downloads the voice model (about 63 MB) into `models/piper`. This first setup requires an internet connection. After the model is downloaded, speech synthesis runs locally without internet access.

The model is downloaded from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/ru/ru_RU/denis/medium). Its model card identifies the source dataset as CC0. Piper itself is distributed under GPL-3.0-or-later; review that license before redistributing an application bundle containing Piper.

The voice model is not stored in GitHub. It is downloaded to the local project folder and verified with a checksum before use.

## 3. Run

```powershell
py main.py
```

1. Wait for the model to load.
2. Hold **Left Ctrl + Left Shift** together and speak to dictate text, or hold **Right Ctrl** and speak a command.
3. Release the key to process the recording.
4. Press **Esc** to exit.

The default model path is `../GigaAM-v3` relative to this project folder. To use another location, set `GIGAAM_MODEL_DIR`:

```powershell
$env:GIGAAM_MODEL_DIR="D:\\AI\\GigaAM-v3"
py main.py
```

Dictation hotkey: `right alt+right shift`. Voice-command hotkey: `right ctrl`.

## Notes

- GigaAM's short-audio `.transcribe()` method supports clips up to 25 seconds; longer recordings are skipped with a message.
- The model files and custom model code are loaded locally. The application does not fetch model weights from Hugging Face when it starts.
- The model repository contains custom Python code. `trust_remote_code=True` is required by GigaAM; only use model files obtained from the official publisher.
- The model weights are not included in this GitHub repository.


## Project modules

The application is split by responsibility so features can be maintained independently:

- `main.py` — startup, microphone hotkeys, speech recognition and command routing.
- `assistant_window.py` — Tkinter command guide and live microphone/listening status.
- `windows_actions.py` — Windows actions: lock, reboot, settings, Downloads, Recycle Bin and screenshots.
- `reminders.py` — reminder parsing, scheduling and background notifications.
- `notifications.py` — Windows toast notifications and local Piper neural speech synthesis.
- `email_manager.py` — Mail.ru SMTP sending and local address-book storage.
- `contact_form.py` — desktop form for manually adding contacts.
- `file_search.py` — web search, MFT search orchestration and results window.
- `folder_organizer.py` — preview-first folder organizer with confirmation before moving files.
- `file_indexer.py` — NTFS MFT indexing and SQLite/FTS search database.

The address book and file index are stored under `%LOCALAPPDATA%\\GigaAMVoiceAssistant`, not in the repository. To add a contact, say **«добавить контакт»** and fill in the name and email address in the form.

## Tkinter interface

After the local model loads, the main Tkinter window displays the command reference, usage steps, microphone availability and current recording/recognition status. Hold Left Ctrl + Left Shift for dictation or Right Ctrl for a voice command; release the keys to process the audio. Close the window to exit.
\n\nTo organize a folder, say **«разбери папку»** while holding Right Ctrl. Choose a folder to preview how its top-level files will be grouped. Nothing moves until you click **«Разложить файлы»** and confirm. Existing files are never overwritten; nested folders are left untouched.\n

## Семантические команды через OpenRouter

GigaAM-v3 по-прежнему распознаёт речь локально. Модуль `intent_router.py` передаёт распознанный текст в OpenRouter, чтобы определить намерение по смыслу, а выполнение остаётся в Python и ограничено списком разрешённых действий. Настройки Windows: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` (по умолчанию `https://openrouter.ai/api/v1`) и `OPENROUTER_MODEL` (по умолчанию `openrouter/free`). В окне есть кнопка «Умная команда…» для ввода задачи своими словами.


## Вопросы подключённому ИИ

Скажи «спроси ИИ» и произнеси вопрос либо нажми кнопку «Спросить ИИ…» в главном окне. Запрос отправляется в OpenRouter с настройками `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` и `OPENROUTER_MODEL`; ответ появляется в отдельном окне. Распознавание голоса остаётся локальным, но текст вопроса и ответ обрабатываются выбранной облачной моделью OpenRouter.
