import json
import secrets
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from pc_controller import PCController

API_ROOT = "https://api.telegram.org"
MAX_UPLOAD_MB = 19
MAX_SEND_MB = 45


class TelegramBotClient:
    def __init__(self, token, on_message, on_status, allowed_user_id=None):
        self.token = token.strip()
        self.on_message = on_message
        self.on_status = on_status
        self.allowed_user_id = int(allowed_user_id) if str(allowed_user_id or "").strip() else None
        self.running = False
        self.offset = 0
        self.thread = None
        self.stop_event = threading.Event()
        self.controller = PCController()
        self.audit_file = Path(__file__).with_name("audit.log")
        self.download_dir = Path(__file__).with_name("downloads")
        self.download_dir.mkdir(exist_ok=True)
        self.token_map = {}
        self.alerts_enabled = False
        self.next_alert_check = 0
        self.last_alert_at = 0
        self._state_lock = threading.Lock()
        self.reconnect_count = 0
        self._connection_lost = False
        self.pending_actions = {}

    def api(self, method, params=None, timeout=20):
        data = urllib.parse.urlencode(params or {}).encode()
        request = urllib.request.Request(f"{API_ROOT}/bot{self.token}/{method}", data=data)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram API error"))
        return payload["result"]

    def keyboard(self):
        return {
            "inline_keyboard": [
                [{"text": "🖥 Дашборд", "callback_data": "view:dashboard"},
                 {"text": "📸 Скриншоты", "callback_data": "menu_screenshot"}],
                [{"text": "📊 Мониторинг", "callback_data": "menu_monitor"},
                 {"text": "⚙️ Система", "callback_data": "menu_system"}],
                [{"text": "📁 Файлы", "callback_data": "menu_files"},
                 {"text": "🪟 Окна", "callback_data": "menu_windows"}],
                [{"text": "📱 Приложения", "callback_data": "menu_apps"},
                 {"text": "🧰 Проекты", "callback_data": "menu_projects"}],
                [{"text": "🔔 Оповещения", "callback_data": "menu_alerts"},
                 {"text": "⏻ Питание", "callback_data": "menu_power"}],
                [{"text": "🎮 Управление", "callback_data": "menu_control"}],
                [{"text": "📋 Журнал", "callback_data": "menu_log"},
                 {"text": "❓ Помощь", "callback_data": "cmd:/help"}],
            ]
        }

    def subkeyboard(self, kind):
        menus = {
            "menu_monitor": [
                [("📊 Процессы", "view:processes"), ("💽 Диски", "cmd:/drives")],
                [("🌐 Сеть", "cmd:/network"), ("🎮 GPU", "cmd:/gpu")],
                [("📈 Полный статус", "cmd:/status"), ("🖥 Дашборд", "view:dashboard")],
                [("⬅️ Назад", "menu:root")],
            ],
            "menu_files": [
                [("🖥 Рабочий стол", "files:desktop"), ("📥 Загрузки", "files:downloads")],
                [("📄 Документы", "files:documents"), ("⬆️ Файл → ПК", "info:upload")],
                [("🔎 Поиск", "info:search"), ("⬅️ Назад", "menu:root")],
            ],
            "menu_windows": [
                [("🪟 Список окон", "view:windows"), ("🖥 Свернуть всё", "confirm:/minimize_all")],
                [("📸 Активное окно", "cmd:/screenshot active"), ("⬅️ Назад", "menu:root")],
            ],
            "menu_apps": [
                [("📝 Блокнот", "cmd:/run notepad"), ("🧮 Калькулятор", "cmd:/run calculator")],
                [("📁 Проводник", "cmd:/run explorer"), ("⛔ Остановить", "info:stop")],
                [("⬅️ Назад", "menu:root")],
            ],
            "menu_projects": [
                [("📦 Список", "cmd:/projects")],
                [("▶️ Tetris", "cmd:/project tkinter-tetris"), ("▶️ Sorter", "cmd:/project tkinter-file-sorter")],
                [("📋 Логи", "view:project_logs"), ("⬅️ Назад", "menu:root")],
            ],
            "menu_system": [
                [("📋 Clipboard", "menu_clip"), ("⌨️ Hotkeys", "menu_hotkeys")],
                [("⚙️ Службы", "menu_services"), ("⬅️ Назад", "menu:root")],
            ],
            "menu_services": [
                [("📋 Список служб", "cmd:/services")],
                [("▶️ Spooler", "confirm:/service_start spooler"), ("⛔ Spooler", "confirm:/service_stop spooler")],
                [("▶️ W32Time", "confirm:/service_start w32time"), ("⛔ W32Time", "confirm:/service_stop w32time")],
                [("▶️ BITS", "confirm:/service_start bits"), ("⛔ BITS", "confirm:/service_stop bits")],
                [("⬅️ Назад", "menu_system")],
            ],
            "menu_clip": [
                [("📋 Прочитать", "cmd:/clip_get"), ("✏️ Записать", "info:clipset")],
                [("⬅️ Назад", "menu_system")],
            ],
            "menu_hotkeys": [
                [("Ctrl+C", "cmd:/hotkey ctrl_c"), ("Ctrl+V", "cmd:/hotkey ctrl_v")],
                [("Alt+Tab", "cmd:/hotkey alt_tab"), ("Ctrl+Shift+Esc", "cmd:/hotkey ctrl_shift_esc")],
                [("Win+D", "cmd:/hotkey win_d"), ("⬅️ Назад", "menu_system")],
            ],
            "menu_screenshot": [
                [("🖥 Весь экран", "cmd:/screenshot full"), ("🪟 Активное окно", "cmd:/screenshot active")],
                [("🖥 Мониторы", "view:monitors"), ("⏱ Задержка 3с", "cmd:/screenshot full 3")],
                [("⬅️ Назад", "menu:root")],
            ],
            "menu_alerts": [
                [("🔔 Включить", "alerts:on"), ("🔕 Выключить", "alerts:off")],
                [("ℹ️ Статус", "alerts:status"), ("⬅️ Назад", "menu:root")],
            ],
            "menu_control": [
                [("🖥 Открыть пульт", "control:screen"), ("🔄 Обновить", "control:screen")],
                [("🖱 Клик", "info:click"), ("⌨️ Ввод текста", "info:type")],
                [("📋 Буфер", "menu_clip")],
                [("Esc", "control:key:esc"), ("Enter", "control:key:enter")],
                [("Alt+Tab", "control:key:alt_tab"), ("⬅️ Назад", "menu:root")],
            ],
            "menu_power": [
                [("🔒 Заблокировать", "confirm:/lock"), ("🖥 Свернуть всё", "confirm:/minimize_all")],
                [("💤 Сон", "confirm:/sleep"), ("🔄 Перезагрузка", "confirm:/restart")],
                [("⏻ Выключение", "confirm:/shutdown"), ("🚪 Выход", "confirm:/logoff")],
                [("⬅️ Назад", "menu:root")],
            ],
            "menu_log": [
                [("📋 Последние действия", "view:log"), ("⬅️ Назад", "menu:root")],
            ],
        }
        rows = menus.get(kind, [[("⬅️ Назад", "menu:root")]])
        return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}

    def send_message(self, chat_id, text, markup=None):
        self.api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4000],
                "reply_markup": json.dumps(markup or self.keyboard(), ensure_ascii=False),
            },
            timeout=15,
        )

    def answer_callback(self, query_id, text="Ок"):
        try:
            self.api("answerCallbackQuery", {"callback_query_id": query_id, "text": text}, timeout=5)
        except Exception:
            pass

    def edit_menu(self, chat_id, message_id, text, markup):
        self.api(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:4000],
                "reply_markup": json.dumps(markup, ensure_ascii=False),
            },
            timeout=10,
        )

    def test(self):
        return self.api("getMe", timeout=10)

    def start(self):
        if self.running:
            return
        self.stop_event.clear()
        self.running = True
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

    def stop(self):
        if not self.running:
            return
        if self.allowed_user_id:
            try:
                self.send_message(
                    self.allowed_user_id,
                    "🔴 PC Bridge остановлен. Прослушивание команд отключено.",
                    self.keyboard(),
                )
            except Exception:
                pass
        self.running = False
        self.stop_event.set()
        self.on_status("offline", "Прослушивание остановлено")

    def _poll(self):
        self.on_status("connecting", "Подключение к Telegram...")
        while self.running and not self.stop_event.is_set():
            try:
                me = self.test()
                self._connection_lost = False
                self.on_status("online", f"Бот @{me.get('username', '')} подключён")
                if self.allowed_user_id:
                    self.send_message(self.allowed_user_id, "🟢 PC Bridge v4 запущен.", self.keyboard())
                break
            except urllib.error.HTTPError as exc:
                self.running = False
                self.on_status("error", f"Telegram отклонил подключение: HTTP {exc.code}")
                return
            except (urllib.error.URLError, ssl.SSLError, ConnectionError, OSError):
                self.reconnect_count += 1
                self._connection_lost = True
                self.on_status("connecting", f"Telegram недоступен — переподключение {self.reconnect_count}")
                self.stop_event.wait(2)
            except Exception as exc:
                self.running = False
                self.on_status("error", f"Ошибка подключения: {exc}")
                return

        while self.running and not self.stop_event.is_set():
            try:
                updates = self.api(
                    "getUpdates",
                    {
                        "offset": self.offset,
                        "timeout": 0,
                        "allowed_updates": json.dumps(["message", "callback_query"]),
                    },
                    timeout=3,
                )
                if self._connection_lost:
                    self._connection_lost = False
                    self.on_status("online", f"Telegram подключён • переподключений: {self.reconnect_count}")
                for update in updates:
                    self.offset = update["update_id"] + 1
                    if update.get("callback_query"):
                        self._callback(update["callback_query"])
                    elif update.get("message"):
                        self._message(update["message"])
                if self.alerts_enabled and time.time() >= self.next_alert_check:
                    self._check_alerts()
                    self.next_alert_check = time.time() + 60
                if not updates:
                    self.stop_event.wait(0.5)
            except (TimeoutError, socket.timeout):
                self.stop_event.wait(0.2)
            except (urllib.error.URLError, ssl.SSLError, ConnectionError, OSError):
                if self.running:
                    if not self._connection_lost:
                        self.reconnect_count += 1
                    self._connection_lost = True
                    self.on_status("connecting", f"Переподключение к Telegram… попытка {self.reconnect_count}")
                    self.stop_event.wait(2)
            except Exception:
                if self.running:
                    if not self._connection_lost:
                        self.reconnect_count += 1
                    self._connection_lost = True
                    self.on_status("connecting", f"Временная ошибка связи — переподключение {self.reconnect_count}")
                    self.stop_event.wait(2)

    def _authorized(self, message):
        return self.allowed_user_id is None or message.get("from", {}).get("id") == self.allowed_user_id

    def _audit(self, user_id, action, result):
        try:
            line = f"{datetime.now().isoformat(timespec='seconds')} | user={user_id} | {action} | {result}\n"
            with self.audit_file.open("a", encoding="utf-8") as file:
                file.write(line)
        except OSError:
            pass

    def _result(self, base, ok, text):
        self._audit(base.get("user_id"), base.get("action", "command"), "SUCCESS" if ok else "FAILED")
        self.on_message({**base, "type": "result", "text": ("SUCCESS: " if ok else "FAILED: ") + text})

    def _message(self, message):
        if not self._authorized(message):
            user = message.get("from", {})
            self._audit(user.get("id"), "UNAUTHORIZED message", "BLOCKED")
            if self.allowed_user_id:
                try:
                    self.send_message(
                        self.allowed_user_id,
                        f"🛡 Заблокирована попытка доступа: user_id={user.get('id')} username=@{user.get('username', '')}",
                        self.keyboard(),
                    )
                except Exception:
                    pass
            return
        chat = message.get("chat", {})
        base = {
            "chat_id": chat.get("id"),
            "user_id": message.get("from", {}).get("id"),
            "first_name": message.get("from", {}).get("first_name", ""),
            "action": "",
        }
        if "text" in message:
            text = message["text"].strip()
            base["action"] = text
            pending = self.pending_actions.pop(base["user_id"], None)
            if pending and not text.startswith("/"):
                action, key = pending
                if action == "rename":
                    ok, reply = self.controller.rename_file(key, text)
                    self.send_message(chat["id"], reply, self.keyboard())
                    self._result(base, ok, reply)
                    return
                if action == "type":
                    ok, reply = self.controller.type_text(text)
                    self.send_message(chat["id"], reply, self.subkeyboard("menu_control"))
                    self._result(base, ok, reply)
                    return
                if action == "click":
                    parts = text.replace(",", " ").split()
                    if len(parts) == 2 and all(part.lstrip("-").isdigit() for part in parts):
                        ok, reply = self.controller.mouse_click(int(parts[0]), int(parts[1]))
                    else:
                        ok, reply = False, "❌ Пришли координаты в формате: 500 300"
                    self.send_message(chat["id"], reply, self.subkeyboard("menu_control"))
                    self._result(base, ok, reply)
                    return
            if text in ("/start", "/help"):
                self.send_message(chat["id"], self.controller.help_text())
                return
            if text.startswith("/"):
                self._execute_and_send(chat["id"], base, text)
        elif "document" in message:
            self._receive_upload(chat["id"], message["document"], base)
        elif "voice" in message:
            self.send_message(
                chat["id"],
                "🎤 Голос получен. Голосовое сохранено в Telegram, но распознавание речи пока не включено.",
                self.keyboard(),
            )
            self.on_message({**base, "type": "voice", "text": "Получено голосовое сообщение."})

    def _execute_and_send(self, chat_id, base, command):
        ok, reply = self.controller.execute(command)
        if reply.startswith("SCREENSHOT:"):
            parts = reply.split(":", 1)[1].split()
            mode = parts[0] if parts else "full"
            monitor = int(parts[1]) if mode == "monitor" and len(parts) > 1 and parts[1].isdigit() else 0
            delay = 3 if "3" in parts[1:] else 0
            path, error = self.controller.screenshot(mode=mode, monitor=monitor, delay=delay)
            if path:
                self.send_photo(chat_id, path)
                self._result(base, True, "📸 Скриншот отправлен.")
            else:
                self.send_message(chat_id, error)
                self._result(base, False, error)
            return
        if reply.startswith("DOWNLOAD:"):
            ok_path, path = self.controller.download_path(reply[9:])
            if ok_path:
                self.send_document(chat_id, Path(path))
                self._result(base, True, "📤 Файл отправлен.")
            else:
                self.send_message(chat_id, path)
                self._result(base, False, path)
            return
        if reply == "ALERTS_ON":
            self.alerts_enabled = True
            self.next_alert_check = 0
            reply = "🔔 Оповещения включены. Проверка CPU/RAM/диска — раз в минуту."
        elif reply == "ALERTS_OFF":
            self.alerts_enabled = False
            reply = "🔕 Оповещения выключены."
        self.send_message(chat_id, reply, self.keyboard())
        self._result(base, ok, reply)

    def _callback(self, query):
        if not self._authorized(query):
            user = query.get("from", {})
            self._audit(user.get("id"), "UNAUTHORIZED callback", "BLOCKED")
            return
        data = query.get("data", "")
        message = query.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        user_id = query.get("from", {}).get("id")
        self.answer_callback(query["id"])

        if data in ("menu:root", "menu_root"):
            self.edit_menu(chat_id, message["message_id"], "🎛 PC BRIDGE v3\nВыбери раздел:", self.keyboard())
            return
        if data.startswith("menu_"):
            title = data.replace("menu_", "").replace("_", " ").title()
            self.edit_menu(chat_id, message["message_id"], f"🎛 {title}", self.subkeyboard(data))
            return
        if data == "view:dashboard":
            self._render_dashboard(chat_id, message["message_id"])
            return
        if data == "control:screen":
            self._send_control_screen(chat_id)
            return
        if data.startswith("control:key:"):
            key = data.split(":", 2)[2]
            ok, reply = self.controller.hotkey(key)
            self.answer_callback(query["id"], "Готово" if ok else "Ошибка")
            self._audit(user_id, "control key " + key, "SUCCESS" if ok else "FAILED")
            return
        if data.startswith("cmd:"):
            self._execute_and_edit(chat_id, message["message_id"], user_id, data[4:])
            return
        if data.startswith("confirm:"):
            action = data[8:]
            self.edit_menu(
                chat_id,
                message["message_id"],
                f"⚠️ ПОДТВЕРЖДЕНИЕ\n\nДействие: {action}\n\nЭто может изменить состояние ПК.",
                {"inline_keyboard": [[
                    {"text": "⚠️ Подтвердить", "callback_data": "yes:" + action},
                    {"text": "❌ Отмена", "callback_data": "menu:root"},
                ]]},
            )
            return
        if data.startswith("yes:"):
            action = data[4:]
            self._execute_and_edit(chat_id, message["message_id"], user_id, action)
            return
        if data.startswith("files:"):
            self._render_folder(chat_id, message["message_id"], data.split(":", 1)[1])
            return
        if data.startswith("nav:"):
            key = self.token_map.get(data[4:])
            if key:
                self._render_folder(chat_id, message["message_id"], key)
            return
        if data.startswith("file:"):
            key = self.token_map.get(data[5:])
            if key:
                self._render_file_actions(chat_id, message["message_id"], key)
            return
        if data.startswith("file_send:"):
            key = self.token_map.get(data[10:])
            if key:
                self._send_local_file(chat_id, user_id, key)
            return
        if data.startswith("file_delete:"):
            key = self.token_map.get(data[12:])
            if key:
                self.edit_menu(
                    chat_id,
                    message["message_id"],
                    f"🗑 Удалить?\n\n{key}",
                    {"inline_keyboard": [[
                        {"text": "🗑 Да, удалить", "callback_data": "delete_yes:" + self._token(key)},
                        {"text": "❌ Отмена", "callback_data": "menu:root"},
                    ]]},
                )
            return
        if data.startswith("delete_yes:"):
            key = self.token_map.get(data[11:])
            if key:
                ok, reply = self.controller.delete_file(key)
                self._audit(user_id, "delete " + key, "SUCCESS" if ok else "FAILED")
                self.edit_menu(chat_id, message["message_id"], reply, self.subkeyboard("menu_files"))
            return
        if data.startswith("file_rename:"):
            key = self.token_map.get(data[12:])
            if key:
                self.pending_actions[user_id] = ("rename", key)
                self.send_message(chat_id, f"✏️ Пришли новое имя для:\n{key}\n\nТолько имя файла, без пути.", self.keyboard())
            return
        if data.startswith("file_copy:"):
            key = self.token_map.get(data[10:])
            if key:
                self.edit_menu(chat_id, message["message_id"], f"📋 Куда скопировать?\n\n{key}", {
                    "inline_keyboard": [
                        [{"text": "🖥 Desktop", "callback_data": "copy_to:" + self._token((key, "desktop"))},
                         {"text": "📥 Downloads", "callback_data": "copy_to:" + self._token((key, "downloads"))}],
                        [{"text": "📄 Documents", "callback_data": "copy_to:" + self._token((key, "documents"))}],
                        [{"text": "❌ Отмена", "callback_data": "menu_files"}],
                    ]
                })
            return
        if data.startswith("copy_to:"):
            pair = self.token_map.get(data[8:])
            if pair:
                key, destination = pair
                ok, reply = self.controller.copy_file(key, destination)
                self._audit(user_id, f"copy {key} -> {destination}", "SUCCESS" if ok else "FAILED")
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data.startswith("file_archive:"):
            key = self.token_map.get(data[13:])
            if key:
                ok, reply = self.controller.archive_file(key)
                self._audit(user_id, "archive " + key, "SUCCESS" if ok else "FAILED")
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data.startswith("file_stats:"):
            key = self.token_map.get(data[11:])
            if key:
                ok, reply = self.controller.path_info(key)
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data.startswith("window:"):
            key = self.token_map.get(data[7:])
            if key:
                self._render_window_actions(chat_id, message["message_id"], key)
            return
        if data.startswith("window_focus:"):
            key = self.token_map.get(data[13:])
            if key:
                ok, reply = self.controller.focus_window(key)
                self._audit(user_id, "focus " + key, "SUCCESS" if ok else "FAILED")
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data.startswith("window_close:"):
            key = self.token_map.get(data[13:])
            if key:
                self.edit_menu(chat_id, message["message_id"], f"⚠️ Закрыть окно?\n\n{key}", {
                    "inline_keyboard": [[
                        {"text": "⚠️ Закрыть", "callback_data": "window_close_yes:" + self._token(key)},
                        {"text": "❌ Отмена", "callback_data": "menu:windows"},
                    ]]
                })
            return
        if data.startswith("window_close_yes:"):
            key = self.token_map.get(data[17:])
            if key:
                ok, reply = self.controller.close_window(key)
                self._audit(user_id, "close " + key, "SUCCESS" if ok else "FAILED")
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data.startswith("window_shot:"):
            key = self.token_map.get(data[12:])
            if key:
                records = {title: hwnd for hwnd, title, _ in self.controller.window_records(50)}
                hwnd = records.get(key)
                if hwnd:
                    path, error = self.controller.screenshot_window(hwnd)
                    if path:
                        self.send_photo(chat_id, path)
                    else:
                        self.send_message(chat_id, error)
            return
        if data == "view:processes":
            self._render_processes(chat_id, message["message_id"])
            return
        if data.startswith("proc:"):
            pid = self.token_map.get(data[5:])
            if pid:
                self._render_process_actions(chat_id, message["message_id"], int(pid))
            return
        if data.startswith("proc_info:"):
            pid = self.token_map.get(data[10:])
            if pid:
                ok, reply = self.controller.process_info(pid)
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data.startswith("proc_kill:"):
            pid = self.token_map.get(data[10:])
            if pid:
                self.edit_menu(chat_id, message["message_id"], f"⚠️ Завершить PID {pid}?", {
                    "inline_keyboard": [[
                        {"text": "⛔ Завершить", "callback_data": "proc_kill_yes:" + self._token(pid)},
                        {"text": "❌ Отмена", "callback_data": "view:processes"},
                    ]]
                })
            return
        if data.startswith("proc_kill_yes:"):
            pid = self.token_map.get(data[14:])
            if pid:
                ok, reply = self.controller.kill_process(pid)
                self._audit(user_id, f"kill {pid}", "SUCCESS" if ok else "FAILED")
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data == "view:windows":
            self._render_windows(chat_id, message["message_id"])
            return
        if data == "view:project_logs":
            self._render_project_logs(chat_id, message["message_id"])
            return
        if data == "view:monitors":
            self._render_monitors(chat_id, message["message_id"])
            return
        if data.startswith("project_log:"):
            name = self.token_map.get(data[12:])
            if name:
                ok, reply = self.controller.project_log(name)
                self.send_message(chat_id, reply, self.keyboard())
            return
        if data == "view:log":
            self.send_message(chat_id, self.controller.audit_summary(self.audit_file), self.keyboard())
            return
        if data == "info:upload":
            self.send_message(chat_id, "⬆️ Просто отправь файл как документ. Он будет атомарно сохранён в Windows Downloads.", self.keyboard())
            return
        if data == "info:search":
            self.send_message(chat_id, "🔎 Поиск: /find downloads имя_файла\nМожно искать в desktop, downloads или documents. Результат можно открыть через кнопки.", self.keyboard())
            return
        if data == "info:stop":
            self.send_message(chat_id, "⛔ Доступны только allow-list приложения: /stop notepad, /stop calculator, /stop explorer.", self.keyboard())
            return
        if data == "info:clipset":
            self.send_message(chat_id, "✏️ Используй /clip_set <текст>. Лимит 4000 символов.", self.keyboard())
            return
        if data == "info:click":
            self.pending_actions[user_id] = ("click", None)
            self.send_message(chat_id, "🖱 Пришли координаты клика следующим сообщением.\nНапример: 500 300", self.subkeyboard("menu_control"))
            return
        if data == "info:type":
            self.pending_actions[user_id] = ("type", None)
            self.send_message(chat_id, "⌨️ Пришли текст следующим сообщением — он будет введён в активное окно.", self.subkeyboard("menu_control"))
            return
        if data.startswith("alerts:"):
            action = data.split(":", 1)[1]
            if action == "on":
                self.alerts_enabled = True
                self.next_alert_check = 0
                self.send_message(chat_id, "🔔 Оповещения включены.", self.keyboard())
            elif action == "off":
                self.alerts_enabled = False
                self.send_message(chat_id, "🔕 Оповещения выключены.", self.keyboard())
            else:
                self.send_message(chat_id, "🔔 Оповещения: " + ("ВКЛ" if self.alerts_enabled else "ВЫКЛ"), self.keyboard())
            return

    def _execute_and_edit(self, chat_id, message_id, user_id, command):
        base = {"chat_id": chat_id, "user_id": user_id, "first_name": "", "action": command}
        ok, reply = self.controller.execute(command)
        if reply.startswith("SCREENSHOT:"):
            parts = reply.split(":", 1)[1].split()
            mode = parts[0] if parts else "full"
            monitor = int(parts[1]) if mode == "monitor" and len(parts) > 1 and parts[1].isdigit() else 0
            delay = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            path, error = self.controller.screenshot(mode=mode, monitor=monitor, delay=delay)
            if path:
                self.send_photo(chat_id, path)
                self._result(base, True, "📸 Скриншот отправлен.")
            else:
                self.send_message(chat_id, error, self.keyboard())
                self._result(base, False, error)
            return
        if reply == "ALERTS_ON":
            self.alerts_enabled = True
            reply = "🔔 Оповещения включены."
        elif reply == "ALERTS_OFF":
            self.alerts_enabled = False
            reply = "🔕 Оповещения выключены."
        self.edit_menu(chat_id, message_id, reply, self.keyboard())
        self._result(base, ok, reply)

    def _token(self, value):
        token = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10]
        self.token_map[token] = value
        if len(self.token_map) > 500:
            self.token_map.clear()
        return token

    def _render_dashboard(self, chat_id, message_id):
        markup = {
            "inline_keyboard": [
                [{"text": "🔄 Обновить", "callback_data": "view:dashboard"}],
                [{"text": "📊 Процессы", "callback_data": "view:processes"},
                 {"text": "💽 Диски", "callback_data": "cmd:/drives"}],
                [{"text": "🌐 Сеть", "callback_data": "cmd:/network"},
                 {"text": "🎮 GPU", "callback_data": "cmd:/gpu"}],
                [{"text": "⬅️ Главное меню", "callback_data": "menu:root"}],
            ]
        }
        self.edit_menu(chat_id, message_id, self.controller.dashboard(), markup)

    def _send_control_screen(self, chat_id):
        path, error = self.controller.screenshot(mode="full")
        if not path:
            self.send_message(chat_id, error, self.subkeyboard("menu_control"))
            return
        monitors = self.controller.monitor_records()
        if monitors:
            _, _, width, height = monitors[0]
            caption = f"🎮 ПУЛЬТ ПК · {width}×{height}\nОбнови снимок после действия."
        else:
            caption = "🎮 ПУЛЬТ ПК\nОбнови снимок после действия."
        markup = {
            "inline_keyboard": [
                [{"text": "🔄 Обновить", "callback_data": "control:screen"}],
                [{"text": "🖱 Клик", "callback_data": "info:click"},
                 {"text": "⌨️ Ввод текста", "callback_data": "info:type"}],
                [{"text": "📋 Буфер", "callback_data": "menu_clip"}],
                [{"text": "Esc", "callback_data": "control:key:esc"},
                 {"text": "Enter", "callback_data": "control:key:enter"},
                 {"text": "Alt+Tab", "callback_data": "control:key:alt_tab"}],
                [{"text": "⬅️ Управление", "callback_data": "menu_control"}],
            ]
        }
        self.send_photo(chat_id, path, caption=caption, markup=markup)

    def _render_folder(self, chat_id, message_id, key):
        ok, listing = self.controller.list_files(key)
        if not ok:
            self.edit_menu(chat_id, message_id, listing, self.subkeyboard("menu_files"))
            return
        target = self.controller.resolve_allowed_path(key, must_exist=True, allow_root=True)
        buttons = []
        parent = "/".join(key.split("/")[:-1])
        if parent:
            buttons.append([{"text": "⬅️ Вверх", "callback_data": "nav:" + self._token(parent)}])
        try:
            items = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            for item in items[:80]:
                item_key = self.controller.relative_key(item)
                if not item_key:
                    continue
                if item.is_dir():
                    buttons.append([{"text": ("📁 " + item.name)[:55], "callback_data": "nav:" + self._token(item_key)}])
                else:
                    buttons.append([{"text": ("📄 " + item.name)[:55], "callback_data": "file:" + self._token(item_key)}])
        except OSError:
            pass
        buttons.append([{"text": "🔎 Поиск", "callback_data": "info:search"}, {"text": "⬅️ Файлы", "callback_data": "menu_files"}])
        self.edit_menu(chat_id, message_id, listing + "\n\n👇 Выбери папку или файл:", {"inline_keyboard": buttons})

    def _render_file_actions(self, chat_id, message_id, key):
        markup = {
            "inline_keyboard": [
                [{"text": "📤 Отправить в Telegram", "callback_data": "file_send:" + self._token(key)}],
                [{"text": "✏️ Переименовать", "callback_data": "file_rename:" + self._token(key)},
                 {"text": "📋 Копировать", "callback_data": "file_copy:" + self._token(key)}],
                [{"text": "📦 Создать ZIP", "callback_data": "file_archive:" + self._token(key)},
                 {"text": "📊 Инфо", "callback_data": "file_stats:" + self._token(key)}],
                [{"text": "🗑 Удалить", "callback_data": "file_delete:" + self._token(key)}],
                [{"text": "⬅️ Назад", "callback_data": "menu_files"}],
            ]
        }
        self.edit_menu(chat_id, message_id, f"📄 {key}\n\nВыбери действие:", markup)

    def _send_local_file(self, chat_id, user_id, key):
        ok, path = self.controller.download_path(key)
        if not ok:
            self.send_message(chat_id, path, self.keyboard())
            return
        file_path = Path(path)
        size = file_path.stat().st_size
        if size > MAX_SEND_MB * 1024 * 1024:
            self.send_message(chat_id, f"❌ Файл {self.controller._size(size)} больше безопасного лимита отправки {MAX_SEND_MB} MB.", self.keyboard())
            return
        try:
            self.send_document(chat_id, file_path)
            self._audit(user_id, "download " + key, "SUCCESS")
            self.on_message({"chat_id": chat_id, "user_id": user_id, "type": "result", "text": f"📤 Отправлен: {key}"})
        except Exception as exc:
            self._audit(user_id, "download " + key, "FAILED")
            self.send_message(chat_id, f"❌ Передача файла: {exc}", self.keyboard())

    def _render_processes(self, chat_id, message_id):
        if not self.controller.psutil:
            self.edit_menu(chat_id, message_id, "❌ Нужен psutil.", self.subkeyboard("menu_monitor"))
            return
        rows = []
        import psutil
        for process in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = process.info
                rows.append((info["memory_info"].rss if info["memory_info"] else 0, info["pid"], info["name"] or "?"))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        rows.sort(reverse=True)
        buttons = []
        for memory, pid, name in rows[:20]:
            token = self._token(pid)
            buttons.append([{"text": f"⚙️ {name[:32]} • PID {pid} • {memory / 1024 / 1024:.0f}MB", "callback_data": "proc:" + token}])
        buttons.append([{"text": "⬅️ Мониторинг", "callback_data": "menu_monitor"}])
        self.edit_menu(chat_id, message_id, "📊 ТОП ПРОЦЕССОВ\n👇 Выбери процесс:", {"inline_keyboard": buttons})

    def _render_process_actions(self, chat_id, message_id, pid):
        ok, info = self.controller.process_info(pid)
        self.edit_menu(chat_id, message_id, info, {
            "inline_keyboard": [
                [{"text": "📋 Подробности", "callback_data": "proc_info:" + self._token(pid)}],
                [{"text": "⛔ Завершить", "callback_data": "proc_kill:" + self._token(pid)}],
                [{"text": "⬅️ Процессы", "callback_data": "view:processes"}],
            ]
        })

    def _render_windows(self, chat_id, message_id):
        records = self.controller.window_records(40)
        buttons = []
        for _, title, _ in records:
            buttons.append([{"text": ("🪟 " + title)[:55], "callback_data": "window:" + self._token(title)}])
        buttons.append([{"text": "⬅️ Окна", "callback_data": "menu_windows"}])
        self.edit_menu(chat_id, message_id, "🪟 ОКНА\n👇 Выбери окно:", {"inline_keyboard": buttons or [[{"text": "⬅️ Назад", "callback_data": "menu_windows"}]]})

    def _render_window_actions(self, chat_id, message_id, title):
        self.edit_menu(chat_id, message_id, f"🪟 {title}\n\nВыбери действие:", {
            "inline_keyboard": [
                [{"text": "🎯 Фокус", "callback_data": "window_focus:" + self._token(title)},
                 {"text": "📸 Скриншот", "callback_data": "window_shot:" + self._token(title)}],
                [{"text": "❌ Закрыть", "callback_data": "window_close:" + self._token(title)}],
                [{"text": "⬅️ Окна", "callback_data": "view:windows"}],
            ]
        })

    def _render_monitors(self, chat_id, message_id):
        monitors = self.controller.monitor_records()
        buttons = []
        for index, (left, top, width, height) in enumerate(monitors):
            buttons.append([{"text": f"🖥 Монитор {index + 1} • {width}x{height}", "callback_data": f"cmd:/screenshot monitor {index}"}])
        buttons.append([{"text": "⬅️ Скриншоты", "callback_data": "menu_screenshot"}])
        self.edit_menu(chat_id, message_id, "🖥 МОНИТОРЫ", {"inline_keyboard": buttons or [[{"text": "⬅️ Назад", "callback_data": "menu_screenshot"}]]})

    def _render_project_logs(self, chat_id, message_id):
        buttons = []
        for name in self.controller.allowed_projects:
            buttons.append([{"text": "📋 " + name, "callback_data": "project_log:" + self._token(name)}])
        buttons.append([{"text": "⬅️ Проекты", "callback_data": "menu_projects"}])
        self.edit_menu(chat_id, message_id, "📋 ЛОГИ ПРОЕКТОВ", {"inline_keyboard": buttons})

    def _check_alerts(self):
        if not self.allowed_user_id or not self.controller.psutil:
            return
        psutil = self.controller.psutil
        try:
            cpu = psutil.cpu_percent(0.2)
            mem = psutil.virtual_memory().percent
            root = Path.home().anchor or "/"
            disk = psutil.disk_usage(root).percent
            warnings = []
            if cpu >= 90:
                warnings.append(f"CPU {cpu:.0f}%")
            if mem >= 90:
                warnings.append(f"RAM {mem:.0f}%")
            if disk >= 90:
                warnings.append(f"диск {disk:.0f}%")
            now = time.time()
            if warnings and now - self.last_alert_at >= 600:
                self.last_alert_at = now
                self.send_message(self.allowed_user_id, "🚨 АВТО-ОПОВЕЩЕНИЕ\n" + "\n".join("• " + x for x in warnings), self.keyboard())
        except Exception:
            pass

    def send_photo(self, chat_id, path, caption="", markup=None):
        with open(path, "rb") as file:
            self._multipart(
                "sendPhoto", chat_id, "photo", Path(path).name, file.read(),
                extra={"caption": caption, "reply_markup": json.dumps(markup, ensure_ascii=False) if markup else ""},
            )

    def send_document(self, chat_id, path):
        with open(path, "rb") as file:
            self._multipart("sendDocument", chat_id, "document", Path(path).name, file.read())

    def _multipart(self, method, chat_id, field, filename, content, extra=None):
        boundary = "----PCBridgeBoundary"
        body = bytearray()
        body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
        )
        for name, value in (extra or {}).items():
            if value:
                body.extend(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
                )
        body.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
        )
        body.extend(content)
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            f"{API_ROOT}/bot{self.token}/{method}",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode())
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram upload failed"))

    def _receive_upload(self, chat_id, document, base):
        file_size = int(document.get("file_size") or 0)
        if file_size > MAX_UPLOAD_MB * 1024 * 1024:
            self.send_message(chat_id, f"❌ Telegram download ограничен {MAX_UPLOAD_MB} MB для надёжной передачи.", self.keyboard())
            return
        try:
            info = self.api("getFile", {"file_id": document["file_id"]})
            file_path = info["file_path"]
            url = f"{API_ROOT}/file/bot{self.token}/{file_path}"
            destination = self.controller.receive_upload_path(document.get("file_name", "upload.bin"))
            temp = destination.with_suffix(destination.suffix + ".part")
            with urllib.request.urlopen(url, timeout=60) as response:
                with temp.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
            temp.replace(destination)
            self.send_message(chat_id, f"✅ Файл загружен в Downloads: {destination.name}", self.keyboard())
            self._audit(base.get("user_id"), "upload " + destination.name, "SUCCESS")
            self.on_message({**base, "type": "result", "text": f"⬆️ Загружен: {destination.name}"})
        except Exception as exc:
            try:
                if "temp" in locals() and temp.exists():
                    temp.unlink()
            except OSError:
                pass
            self._audit(base.get("user_id"), "upload", "FAILED")
            self.send_message(chat_id, f"❌ Upload: {exc}", self.keyboard())
