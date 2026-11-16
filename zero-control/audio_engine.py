"""Запись, локальное распознавание и обработка голосового ввода Zero Control."""
from __future__ import annotations

import os
import queue
import shutil
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Callable, Any


class AudioEngine:
    """Изолирует аудиоустройство, буфер записи и модель GigaAM от main.py."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    MAX_CHUNK_SECONDS = 24

    def __init__(
        self,
        get_ui: Callable[[], Any],
        update_ui_status: Callable[..., None],
        handle_command: Callable[[str], None],
    ) -> None:
        self._get_ui = get_ui
        self._update_ui_status = update_ui_status
        self._handle_command = handle_command

        self._model = None
        self._stream = None
        self._audio_chunks = []
        self._recording = False
        self._recording_mode = "text"
        self._lock = threading.Lock()
        self._transcription_lock = threading.Lock()
        self._speech_audio_queue = None
        self._speech_stop_token = None
        self._speech_stream_thread = None
        self._speech_mode_state = None
        self._speech_sample_count = 0

        self.imageio_ffmpeg = None
        self.keyboard = None
        self.np = None
        self.pyperclip = None
        self.sd = None
        self.sf = None
        self.torch = None
        self.AutoModel = None
        self.model_dir = None
        self.speech_engine = "gigaam"

    @property
    def requires_local_model(self) -> bool:
        return self.speech_engine == "gigaam"

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    @property
    def is_dictation_active(self) -> bool:
        with self._lock:
            return self._recording and self._recording_mode == "text"

    def load_dependencies(self) -> None:
        """Загружает аудиозависимости выбранного движка."""
        from agent_core import load_settings

        selected = str(load_settings().get("speech_engine", "gigaam")).strip().lower()
        self.speech_engine = selected if selected in ("gigaam", "speechkit") else "gigaam"

        import keyboard
        import numpy
        import pyperclip
        import sounddevice
        import soundfile

        self.keyboard = keyboard
        self.np = numpy
        self.pyperclip = pyperclip
        self.sd = sounddevice
        self.sf = soundfile

        if self.requires_local_model:
            import imageio_ffmpeg
            import torch
            from transformers import AutoModel

            self.imageio_ffmpeg = imageio_ffmpeg
            self.torch = torch
            self.AutoModel = AutoModel

            project_dir = Path(__file__).resolve().parent
            self.model_dir = Path(
                os.getenv(
                    "ZERO_CONTROL_MODEL_DIR",
                    os.getenv("GIGAAM_MODEL_DIR", str(project_dir.parent / "GigaAM-v3")),
                )
            ).expanduser().resolve()
        else:
            print("Выбран Yandex SpeechKit: локальная модель GigaAM не загружается.", flush=True)

    def configure_ffmpeg(self) -> None:
        if self.imageio_ffmpeg is None:
            return
        source = Path(self.imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        target_dir = Path(tempfile.gettempdir()) / "zero_control_ffmpeg"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "ffmpeg.exe"
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        os.environ["PATH"] = str(target_dir) + os.pathsep + os.environ.get("PATH", "")

    def check_microphone(self) -> bool:
        try:
            device = self.sd.query_devices(kind="input")
            if device["max_input_channels"] < self.CHANNELS:
                return False
        except (self.sd.PortAudioError, OSError):
            return False
        return True

    def load_model(self) -> None:
        if not (self.model_dir / "config.json").is_file():
            raise FileNotFoundError(
                f"Локальная модель GigaAM не найдена: {self.model_dir}\n"
                "Поместите модель ai-sage/GigaAM-v3 (revision e2e_rnnt) "
                "в папку GigaAM-v3 рядом с папкой приложения."
            )
        self._model = self.AutoModel.from_pretrained(
            str(self.model_dir), trust_remote_code=True, local_files_only=True
        )
        self._model.eval()

    def audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"Состояние аудиоустройства: {status}")
        with self._lock:
            if not self._recording:
                return
            if self.speech_engine == "speechkit":
                audio_queue = self._speech_audio_queue
                self._speech_sample_count += len(indata)
            else:
                self._audio_chunks.append(indata.copy())
                audio_queue = None
        if audio_queue is not None:
            audio_queue.put_nowait(indata.copy())

    def start_recording(self, mode: str) -> None:
        with self._lock:
            if self._recording:
                return
            self._audio_chunks = []
            self._recording_mode = mode
            self._recording = True
            self._speech_sample_count = 0
            self._speech_mode_state = {"mode": mode}
            self._speech_audio_queue = queue.Queue() if self.speech_engine == "speechkit" else None
            self._speech_stop_token = object() if self.speech_engine == "speechkit" else None
        try:
            self._update_ui_status(
                "ИДЁТ ДИКТОВКА" if mode == "text" else "СЛУШАЮ ГОЛОСОВУЮ КОМАНДУ",
                recording=mode,
            )
            ui = self._get_ui()
            if ui is not None:
                ui.root.update_idletasks()
                ui.root.update()
            self._stream = self.sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="float32",
                callback=self.audio_callback,
            )
            self._stream.start()
            if self.speech_engine == "speechkit":
                self._speech_stream_thread = threading.Thread(
                    target=self._run_speechkit_stream,
                    args=(self._speech_audio_queue, self._speech_stop_token, self._speech_mode_state),
                    daemon=True,
                )
                self._speech_stream_thread.start()
            key_name = "Right Ctrl+Right Shift" if mode == "text" else "правый Ctrl"
            purpose = "для ввода текста" if mode == "text" else "для голосовой команды"
            print(f"Идёт запись {purpose}. Отпустите {key_name}, чтобы выполнить.")
        except (self.sd.PortAudioError, OSError) as exc:
            with self._lock:
                self._recording = False
            self._stream = None
            print(f"Не удалось начать запись: {exc}")
            self._update_ui_status("ОШИБКА ЗАПИСИ", recording=False)

    def promote_to_dictation(self) -> None:
        """Переключает активную запись правого Ctrl в режим диктовки."""
        with self._lock:
            if not self._recording or self._recording_mode == "text":
                return
            self._recording_mode = "text"
            if self._speech_mode_state is not None:
                self._speech_mode_state["mode"] = "text"
        print("Режим переключён на диктовку: удерживайте Right Ctrl + Right Shift.")
        self._update_ui_status("ДИКТОВКА", recording="text")

    def stop_recording(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            chunks = list(self._audio_chunks)
            mode = self._recording_mode
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        self._update_ui_status("РАСПОЗНАЮ РЕЧЬ", recording=False)
        if self.speech_engine == "speechkit":
            with self._lock:
                audio_queue = self._speech_audio_queue
                stop_token = self._speech_stop_token
                sample_count = self._speech_sample_count
                if self._speech_mode_state is not None:
                    self._speech_mode_state["mode"] = mode
                self._speech_audio_queue = None
            if audio_queue is not None:
                audio_queue.put_nowait(stop_token)
            if sample_count == 0:
                print("Звук не записан: микрофон не передал аудиоданные.")
                self._update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
            return
        if not chunks:
            print("Звук не записан: микрофон не передал аудиоданные.")
            self._update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
            return
        audio_data = self.np.concatenate(chunks, axis=0).reshape(-1)
        if audio_data.size == 0:
            print("Звук не записан.")
            return
        print(f"Запись завершена: {len(audio_data) / self.SAMPLE_RATE:.2f} сек.")
        worker = self.transcribe_and_paste if mode == "text" else self.transcribe_and_execute
        threading.Thread(target=worker, args=(audio_data,), daemon=True).start()

    def _run_speechkit_stream(self, audio_queue, stop_token, mode_state) -> None:
        if not self._transcription_lock.acquire(blocking=False):
            print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
            while True:
                item = audio_queue.get()
                if item is stop_token:
                    break
            return
        try:
            from speechkit_engine import transcribe_audio_stream

            print("Потоковое распознавание через Yandex SpeechKit v3...", flush=True)
            text = transcribe_audio_stream(
                audio_queue,
                stop_token,
                numpy_module=self.np,
                on_partial=lambda partial: self._update_ui_status(transcript=partial),
            )
            mode = mode_state["mode"]
            if text:
                if mode == "text":
                    self._paste_transcription(text)
                else:
                    self._handle_command(text)
                print(f"Текст распознан и обработан: {text}", flush=True)
            else:
                print("Речь не распознана.")
        except Exception as exc:
            print(f"Ошибка потокового распознавания: {exc}")
            traceback.print_exc()
        finally:
            self._transcription_lock.release()
            self._update_ui_status(
                "ОЖИДАЮ НАЖАТИЯ RIGHT CTRL",
                recording=False,
                transcript="",
            )

    def transcribe_audio_file(self, audio_data) -> str:
        if self.speech_engine == "speechkit":
            from speechkit_engine import transcribe_audio

            return transcribe_audio(
                audio_data,
                sample_rate=self.SAMPLE_RATE,
                numpy_module=self.np,
            )

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_path = Path(tmp.name)
            self.sf.write(str(temp_path), audio_data, self.SAMPLE_RATE, subtype="PCM_16")
            with self.torch.inference_mode():
                return self._model.transcribe(str(temp_path)).strip()
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def transcribe_parts(self, audio_data, label: str) -> str:
        chunk_size = self.SAMPLE_RATE * self.MAX_CHUNK_SECONDS
        parts = [
            audio_data[i:i + chunk_size]
            for i in range(0, len(audio_data), chunk_size)
        ]
        results = []
        for index, part in enumerate(parts, start=1):
            if len(parts) > 1:
                print(f"Распознаю {label} {index} из {len(parts)}...")
            result = self.transcribe_audio_file(part)
            if result:
                results.append(result)
        return " ".join(results).strip()

    def _paste_transcription(self, text: str) -> None:
        try:
            from agent_core import load_settings
            if load_settings().get("clean_dictation_with_ai", False):
                print("Очищаю текст диктовки с помощью ИИ...")
                from groq_client import chat
                cleaned = chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Ты редактор расшифровки русской устной речи. "
                                "Убери слова-паразиты, случайные повторы, запинки, "
                                "оговорки и незавершённые дубли фраз. Сохрани исходный "
                                "смысл, факты, имена, числа и стиль говорящего. "
                                "Не пересказывай и не сокращай содержательные мысли, "
                                "не добавляй ничего от себя. Верни только готовый текст "
                                "без пояснений и кавычек."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    temperature=0.1,
                    max_tokens=max(300, min(2000, len(text) // 2 + 200)),
                    timeout=60,
                ).strip()
                if cleaned:
                    text = cleaned
                    print("ИИ-очистка диктовки завершена.")
                else:
                    print("ИИ вернул пустой текст; использую исходную расшифровку.")
        except Exception as exc:
            print(f"Не удалось очистить диктовку через ИИ; использую исходный текст: {exc}")
        self.pyperclip.copy(text)
        self.keyboard.send("ctrl+v")
        print(f"Текст распознан и вставлен: {text}")

    def transcribe_and_paste(self, audio_data) -> None:
        if not self._transcription_lock.acquire(blocking=False):
            print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
            return
        try:
            engine_label = "через Yandex SpeechKit v3" if self.speech_engine == "speechkit" else "локально"
            print(f"Распознаю речь {engine_label}...")
            text = self.transcribe_parts(audio_data, "фрагмент")
            if text:
                self._paste_transcription(text)
            else:
                print("Речь не распознана.")
        except Exception as exc:
            print(f"Ошибка распознавания: {exc}")
            traceback.print_exc()
        finally:
            self._transcription_lock.release()
            self._update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")

    def transcribe_and_execute(self, audio_data) -> None:
        if not self._transcription_lock.acquire(blocking=False):
            print("Предыдущее распознавание ещё выполняется. Эта запись пропущена.")
            return
        try:
            print("Распознаю голосовую команду...")
            text = self.transcribe_parts(audio_data, "фрагмент команды")
            if text:
                try:
                    self._handle_command(text)
                except Exception as exc:
                    print(f"Ошибка выполнения команды: {exc}")
                    traceback.print_exc()
            else:
                print("Голосовая команда не распознана.")
        except Exception as exc:
            print(f"Ошибка распознавания команды: {exc}")
            traceback.print_exc()
        finally:
            self._transcription_lock.release()
            self._update_ui_status("ОЖИДАЮ НАЖАТИЯ RIGHT CTRL")
