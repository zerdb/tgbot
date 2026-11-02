# Voice to Text — Local GigaAM-v3

Offline push-to-talk voice typing for Windows. Hold **Right Ctrl** to record; release it to transcribe with a locally stored GigaAM-v3 model and paste the recognized text into the active window.

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

## 3. Run

```powershell
py main.py
```

1. Wait for the model to load.
2. Hold **Right Ctrl** and speak.
3. Release **Right Ctrl**. The recognized text is copied to the clipboard and pasted into the active window.
4. Press **Esc** to exit.

The default model path is `../GigaAM-v3` relative to this project folder. To use another location, set `GIGAAM_MODEL_DIR`:

```powershell
$env:GIGAAM_MODEL_DIR="D:\\AI\\GigaAM-v3"
py main.py
```

Optional setting: `PUSH_TO_TALK_KEY` changes the recording key (default: `right ctrl`).

## Notes

- GigaAM's short-audio `.transcribe()` method supports clips up to 25 seconds; longer recordings are skipped with a message.
- The model files and custom model code are loaded locally. The application does not fetch model weights from Hugging Face when it starts.
- The model repository contains custom Python code. `trust_remote_code=True` is required by GigaAM; only use model files obtained from the official publisher.
- The model weights are not included in this GitHub repository.
