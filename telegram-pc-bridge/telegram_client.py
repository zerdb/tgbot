import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = "https://api.telegram.org"

class TelegramBotClient:
    def __init__(self, token, on_message, on_status):
        self.token = token.strip()
        self.on_message = on_message
        self.on_status = on_status
        self.running = False
        self.offset = 0
        self.thread = None
        self.download_dir = Path(__file__).with_name("downloads")
        self.download_dir.mkdir(exist_ok=True)

    def api(self, method, params=None, timeout=35):
        data = urllib.parse.urlencode(params or {}).encode()
        request = urllib.request.Request(f"{API_ROOT}/bot{self.token}/{method}", data=data)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram API error"))
        return payload["result"]

    def test(self):
        return self.api("getMe", timeout=10)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _poll(self):
        self.on_status("connecting", "Подключение к Telegram...")
        try:
            me = self.test()
            self.on_status("online", f"Бот @{me.get('username', '')} подключён")
        except Exception as exc:
            self.running = False
            self.on_status("error", f"Ошибка подключения: {exc}")
            return

        while self.running:
            try:
                updates = self.api("getUpdates", {
                    "offset": self.offset,
                    "timeout": 25,
                    "allowed_updates": json.dumps(["message"])
                }, timeout=32)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    message = update.get("message")
                    if message:
                        self._handle_message(message)
            except Exception as exc:
                if self.running:
                    self.on_status("error", f"Ошибка связи: {exc}")

        self.on_status("offline", "Прослушивание остановлено")

    def _handle_message(self, message):
        sender = message.get("from", {})
        chat = message.get("chat", {})
        base = {
            "message_id": message.get("message_id"),
            "chat_id": chat.get("id"),
            "user_id": sender.get("id"),
            "username": sender.get("username", ""),
            "first_name": sender.get("first_name", ""),
            "date": message.get("date"),
        }

        if "text" in message:
            self.on_message({**base, "type": "text", "text": message["text"]})
            return

        if "voice" in message:
            voice = message["voice"]
            try:
                path = self.download_file(voice["file_id"], f"voice_{message.get('message_id')}.ogg")
                self.on_message({
                    **base,
                    "type": "voice",
                    "text": f"Голосовое сообщение • {voice.get('duration', 0)} сек.",
                    "file": str(path),
                    "duration": voice.get("duration", 0),
                })
            except Exception as exc:
                self.on_message({**base, "type": "voice", "text": f"Не удалось скачать голосовое: {exc}", "file": ""})
            return

        self.on_message({**base, "type": "other", "text": "Получено неподдерживаемое сообщение"})

    def download_file(self, file_id, filename):
        info = self.api("getFile", {"file_id": file_id}, timeout=15)
        file_path = info["file_path"]
        url = f"{API_ROOT}/file/bot{self.token}/{file_path}"
        destination = self.download_dir / filename
        urllib.request.urlretrieve(url, destination)
        return destination
