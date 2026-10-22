import getpass
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

STARTED_AT = time.time()

class PCController:
    """Strict allow-list controller. No arbitrary shell commands are accepted."""

    def __init__(self):
        home = Path.home()
        self.allowed_folders = {
            "desktop": home / "Desktop",
            "downloads": home / "Downloads",
            "documents": home / "Documents",
        }
        self.allowed_apps = self._build_apps()

    def _build_apps(self):
        if sys.platform.startswith("win"):
            return {
                "notepad": ["notepad.exe"],
                "calculator": ["calc.exe"],
                "explorer": ["explorer.exe"],
            }
        if sys.platform == "darwin":
            return {
                "textedit": ["open", "-a", "TextEdit"],
                "calculator": ["open", "-a", "Calculator"],
                "finder": ["open", str(Path.home())],
            }
        return {
            "files": ["xdg-open", str(Path.home())],
        }

    def help_text(self):
        apps = ", ".join(self.allowed_apps)
        folders = ", ".join(self.allowed_folders)
        return (
            "🕹 Команды PC Bridge\n\n"
            "/status — подробный статус ПК\n"
            "/apps — разрешённые приложения\n"
            "/run <имя> — запустить приложение\n"
            "/files <папка> — показать файлы\n"
            "/help — эта справка\n\n"
            f"Приложения: {apps}\n"
            f"Папки: {folders}"
        )

    def execute(self, text):
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1].strip().lower() if len(parts) > 1 else ""

        if command in ("/help", "/start"):
            return True, self.help_text()
        if command == "/status":
            return True, self.status()
        if command == "/apps":
            return True, "🧩 Разрешённые приложения:\n" + "\n".join(f"• {name}" for name in self.allowed_apps)
        if command == "/run":
            return self.run_app(arg)
        if command == "/files":
            return self.list_files(arg)
        return False, "❌ Неизвестная команда. Отправьте /help."

    def status(self):
        root = Path.home().anchor or "/"
        usage = shutil.disk_usage(root)
        uptime = max(0, int(time.time() - STARTED_AT))
        hours, rem = divmod(uptime, 3600)
        minutes, seconds = divmod(rem, 60)
        ip = self._local_ip()
        return (
            "🖥 СТАТУС КОМПЬЮТЕРА\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"✅ PC Bridge: работает\n"
            f"👤 Пользователь: {getpass.getuser()}\n"
            f"💻 Имя ПК: {socket.gethostname()}\n"
            f"🪟 ОС: {platform.system()} {platform.release()}\n"
            f"🏗 Архитектура: {platform.machine()}\n"
            f"🐍 Python: {platform.python_version()}\n"
            f"🌐 Локальный IP: {ip}\n"
            f"⏱ Bridge запущен: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
            f"💾 Диск {root}: {self._gb(usage.used)} / {self._gb(usage.total)} GB "
            f"({usage.used / usage.total * 100:.1f}% занято)\n"
            f"📦 Свободно: {self._gb(usage.free)} GB"
        )

    def _local_ip(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "недоступен"
        finally:
            sock.close()

    @staticmethod
    def _gb(value):
        return f"{value / (1024 ** 3):.1f}"

    def run_app(self, name):
        if not name:
            return False, "❌ Укажите приложение. Пример: /run notepad"
        command = self.allowed_apps.get(name)
        if not command:
            return False, f"⛔ Приложение «{name}» не разрешено. Используйте /apps."
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"✅ Команда выполнена: «{name}» запущено."
        except Exception as exc:
            return False, f"❌ Не удалось запустить «{name}»: {exc}"

    def list_files(self, name):
        if not name:
            return False, "❌ Укажите папку: /files desktop, downloads или documents"
        folder = self.allowed_folders.get(name)
        if not folder:
            return False, "⛔ Эта папка не разрешена. Доступны: " + ", ".join(self.allowed_folders)
        if not folder.exists():
            return False, f"❌ Папка не найдена: {folder}"
        try:
            items = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            shown = items[:40]
            lines = [f"📂 {name} • объектов: {len(items)}", ""]
            for item in shown:
                marker = "📁" if item.is_dir() else "📄"
                lines.append(f"{marker} {item.name}")
            if len(items) > len(shown):
                lines.append(f"\n…ещё {len(items) - len(shown)}")
            return True, "\n".join(lines)
        except Exception as exc:
            return False, f"❌ Ошибка чтения папки: {exc}"
