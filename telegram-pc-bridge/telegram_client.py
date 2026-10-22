import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from pc_controller import PCController

API_ROOT = "https://api.telegram.org"

class TelegramBotClient:
    def __init__(self, token, on_message, on_status, allowed_user_id=None):
        self.token = token.strip()
        self.on_message = on_message
        self.on_status = on_status
        self.allowed_user_id = int(allowed_user_id) if str(allowed_user_id or "").strip() else None
        self.running = False
        self.offset = 0
        self.thread = None
        self.controller = PCController()
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

    def send_message(self, chat_id, text):
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
        for chunk in chunks:
            self.api("sendMessage", {"chat_id": chat_id, "text": chunk}, timeout=15)

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
                    "offset": self.offset, "timeout": 2,
                    "allowed_updates": json.dumps(["message"])
                }, timeout=5)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    message = update.get("message")
                    if message:
                        self._handle_message(message)
            except Exception as exc:
                if self.running:
                    self.on_status("error", f"Ошибка связи: {exc}")

        self.on_status("offline", "Прослушивание остановлено")

    def _authorized(self, message):
        user_id = message.get("from", {}).get("id")
        return self.allowed_user_id is None or user_id == self.allowed_user_id

    def _handle_message(self, message):
        sender = message.get("from", {})
        chat = message.get("chat", {})
        base = {
            "message_id": message.get("message_id"), "chat_id": chat.get("id"),
            "user_id": sender.get("id"), "username": sender.get("username", ""),
            "first_name": sender.get("first_name", ""), "date": message.get("date"),
        }

        if not self._authorized(message):
            self.on_message({**base, "type": "security", "text": "Заблокирована команда от неразрешённого пользователя"})
            return

        if "text" in message:
            text = message["text"]
            self.on_message({**base, "type": "text", "text": text})
            if text.startswith("/"):
                ok, reply = self.controller.execute(text)
                try:
                    self.send_message(chat["id"], reply)
                    self.on_message({**base, "type": "result", "text": ("SUCCESS: " if ok else "FAILED: ") + reply})
                except Exception as exc:
                    self.on_message({**base, "type": "result", "text": f"FAILED: не удалось отправить ответ: {exc}"})
            return

        if "voice" in message:
            voice = message["voice"]
            try:
                path = self.download_file(voice["file_id"], f"voice_{message.get('message_id')}.ogg")
                self.on_message({**base, "type": "voice", "text": f"Голосовое сообщение • {voice.get('duration', 0)} сек.", "file": str(path)})
                self.send_message(chat["id"], "✅ Голосовое получено и сохранено на компьютере.")
            except Exception as exc:
                self.on_message({**base, "type": "voice", "text": f"Не удалось скачать голосовое: {exc}", "file": ""})
                try:
                    self.send_message(chat["id"], f"❌ Голосовое получить не удалось: {exc}")
                except Exception:
                    pass
            return

        self.on_message({**base, "type": "other", "text": "Получено неподдерживаемое сообщение"})

    def download_file(self, file_id, filename):
        info = self.api("getFile", {"file_id": file_id}, timeout=15)
        url = f"{API_ROOT}/file/bot{self.token}/{info['file_path']}"
        destination = self.download_dir / filename
        urllib.request.urlretrieve(url, destination)
        return destination
