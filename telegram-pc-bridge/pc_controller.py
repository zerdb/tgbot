import ctypes
import getpass
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import win32gui
    import win32con
    import win32process
    import win32service
    import win32serviceutil
except ImportError:
    win32gui = win32con = win32process = win32service = win32serviceutil = None

STARTED_AT = time.time()

class PCController:
    """PC controls exposed only through explicit allow-lists."""

    def __init__(self):
        home = Path.home()
        self.allowed_folders = {
            "desktop": home / "Desktop",
            "downloads": home / "Downloads",
            "documents": home / "Documents",
        }
        self.allowed_apps = self._build_apps()
        self.allowed_hotkeys = {
            "ctrl_shift_esc": ("ctrl", "shift", "esc"),
            "alt_tab": ("alt", "tab"),
            "win_d": ("win", "d"),
            "ctrl_c": ("ctrl", "c"),
            "ctrl_v": ("ctrl", "v"),
            "ctrl_s": ("ctrl", "s"),
            "ctrl_w": ("ctrl", "w"),
        }
        self.allowed_services = {
            "spooler": "Spooler",
            "w32time": "W32Time",
            "bits": "BITS",
        }
        self.allowed_projects = self._find_projects()

    def _build_apps(self):
        if os.name == "nt":
            return {"notepad": ["notepad.exe"], "calculator": ["calc.exe"], "explorer": ["explorer.exe"]}
        if sys.platform == "darwin":
            return {"textedit": ["open", "-a", "TextEdit"], "calculator": ["open", "-a", "Calculator"], "finder": ["open", str(Path.home())]}
        return {"files": ["xdg-open", str(Path.home())]}

    def _find_projects(self):
        root = Path(__file__).resolve().parents[1]
        result = {}
        for folder in ("tkinter-file-sorter", "tkinter-tetris", "telegram-pc-bridge"):
            path = root / folder
            main = path / ("main.py" if (path / "main.py").exists() else ("tetris.py" if folder == "tkinter-tetris" else "tkinter_file_sorter.py" if folder == "tkinter-file-sorter" else "main.py"))
            if main.exists():
                result[folder] = main
        return result

    def help_text(self):
        return (
            "🎛 PC BRIDGE v2\n\n"
            "🖥 /status  📊 /processes\n"
            "📱 /apps  ▶ /run <app>  ⛔ /stop <app>\n"
            "📁 /files <desktop|downloads|documents>\n"
            "🪟 /windows  🔽 /minimize_all  🔒 /lock\n"
            "📸 /screenshot  📋 /clip_get  ✏ /clip_set <text>\n"
            "⌨ /hotkey <allow-list>  📦 /projects\n"
            "▶ /project <allow-list project>\n"
            "💽 /drives  🌐 /network\n"
            "⚙ /services  (только allow-list служб)\n"
            "⬆️ /upload и 📤 /download работают через разрешённые папки\n"
            "⚠️ Опасные действия требуют подтверждения в Telegram."
        )

    def execute(self, text):
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if command in ("/help", "/start"): return True, self.help_text()
        if command == "/status": return True, self.status()
        if command == "/apps": return True, "🧩 Приложения:\n" + "\n".join("• "+x for x in self.allowed_apps)
        if command == "/run": return self.run_app(arg.lower())
        if command == "/stop": return self.stop_allowed_app(arg.lower())
        if command == "/files": return self.list_files(arg.lower())
        if command == "/processes": return True, self.processes()
        if command == "/windows": return True, self.windows_list()
        if command == "/minimize_all": return self.minimize_all()
        if command == "/lock": return self.lock_windows()
        if command == "/screenshot": return True, "SCREENSHOT"
        if command == "/clip_get": return self.clip_get()
        if command == "/clip_set": return self.clip_set(arg)
        if command == "/hotkey": return self.hotkey(arg.lower())
        if command == "/projects": return True, self.projects()
        if command == "/project": return self.run_project(arg.lower())
        if command == "/drives": return True, self.drives()
        if command == "/network": return True, self.network()
        if command == "/services": return True, self.services()
        if command == "/service_start": return self.service_action(arg.lower(), "start")
        if command == "/service_stop": return self.service_action(arg.lower(), "stop")
        return False, "❌ Неизвестная команда. /help"

    def status(self):
        root = Path.home().anchor or "/"
        usage = shutil.disk_usage(root)
        uptime = int(time.time() - STARTED_AT)
        cpu = psutil.cpu_percent(0.5) if psutil else 0
        mem = psutil.virtual_memory() if psutil else None
        net = psutil.net_io_counters() if psutil else None
        return (
            "🖥 СТАТУС ПК\n━━━━━━━━━━━━━━━━━━\n"
            f"✅ Bridge: работает\n👤 {getpass.getuser()}\n💻 {socket.gethostname()}\n"
            f"🪟 {platform.system()} {platform.release()}\n🐍 Python {platform.python_version()}\n"
            f"⚡ CPU: {cpu:.1f}%\n"
            f"🧠 RAM: {mem.percent:.1f}% ({self._gb(mem.used)} / {self._gb(mem.total)} GB)\n" if mem else ""
        ) + (
            f"🌐 IP: {self._local_ip()}\n⏱ Bridge: {uptime//3600:02d}:{(uptime%3600)//60:02d}:{uptime%60:02d}\n"
            f"💽 Диск {root}: {self._gb(usage.used)} / {self._gb(usage.total)} GB ({usage.used/usage.total*100:.1f}%)\n"
            f"📦 Свободно: {self._gb(usage.free)} GB\n"
            + (f"🌐 Сеть: ↑ {net.bytes_sent/1024/1024:.1f} MB / ↓ {net.bytes_recv/1024/1024:.1f} MB" if net else "")
        )

    def _local_ip(self):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try: s.connect(("8.8.8.8",80)); return s.getsockname()[0]
        except OSError: return "недоступен"
        finally: s.close()

    @staticmethod
    def _gb(v): return f"{v/(1024**3):.1f}"

    def processes(self):
        if not psutil: return "❌ Установите psutil."
        rows=[]
        for p in psutil.process_iter(["pid","name","memory_info","cpu_percent"]):
            try:
                i=p.info; rows.append(((i["memory_info"].rss if i["memory_info"] else 0),i["pid"],i["name"] or "?",i["cpu_percent"] or 0))
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        rows.sort(reverse=True)
        return "📊 ТОП ПРОЦЕССОВ\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(f"• {n} | PID {pid} | RAM {m/1024/1024:.1f} MB | CPU {cpu:.1f}%" for m,pid,n,cpu in rows[:20])

    def windows_list(self):
        if win32gui is None: return "❌ Для окон нужен pywin32."
        rows=[]
        def cb(hwnd,_):
            if win32gui.IsWindowVisible(hwnd):
                title=win32gui.GetWindowText(hwnd).strip()
                if title:
                    try: _,pid=win32process.GetWindowThreadProcessId(hwnd)
                    except Exception: pid=0
                    rows.append((title,pid))
            return True
        win32gui.EnumWindows(cb,None)
        return "🪟 ОКНА\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(f"• {title} | PID {pid}" for title,pid in rows[:50])

    def list_files(self,name):
        folder=self.allowed_folders.get(name)
        if not folder: return False,"⛔ Папка не разрешена."
        if not folder.exists(): return False,f"❌ Не найдена: {folder}"
        try:
            items=sorted(folder.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower()))
            lines=[f"📂 {name} • {len(items)} объектов",""]+[("📁 " if p.is_dir() else "📄 ")+p.name for p in items[:50]]
            if len(items)>50: lines.append(f"…ещё {len(items)-50}")
            return True,"\n".join(lines)
        except Exception as e: return False,f"❌ {e}"

    def run_app(self,name):
        cmd=self.allowed_apps.get(name)
        if not cmd: return False,"⛔ Приложение не входит в allow-list."
        try: subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); return True,f"✅ {name} запущено."
        except Exception as e: return False,f"❌ {e}"

    def stop_allowed_app(self,name):
        if not psutil or name not in self.allowed_apps: return False,"⛔ Приложение не входит в allow-list."
        targets={"notepad":{"notepad.exe"},"calculator":{"calc.exe","calculatorapp.exe"},"explorer":{"explorer.exe"}}.get(name,set())
        count=0
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info["name"] or "").lower() in targets: p.terminate(); count+=1
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        return (True,f"✅ {name}: остановлено {count}.") if count else (False,f"ℹ️ {name} не запущено.")

    def minimize_all(self):
        if os.name!="nt": return False,"Только Windows."
        try:
            ctypes.windll.user32.keybd_event(0x5B,0,0,0); ctypes.windll.user32.keybd_event(0x44,0,0,0); ctypes.windll.user32.keybd_event(0x44,2,0,0); ctypes.windll.user32.keybd_event(0x5B,2,0,0)
            return True,"🖥 Все окна свернуты."
        except Exception as e: return False,f"❌ {e}"

    def lock_windows(self):
        if os.name!="nt": return False,"Только Windows."
        try: return (True,"🔒 ПК заблокирован.") if ctypes.windll.user32.LockWorkStation() else (False,"❌ Windows не подтвердила.")
        except Exception as e: return False,f"❌ {e}"

    def screenshot(self):
        if not pyautogui: return None,"❌ Нужен pyautogui."
        path=Path(__file__).with_name("downloads")/"screen.png"
        try: pyautogui.screenshot().save(path); return path,""
        except Exception as e: return None,f"❌ {e}"

    def clip_get(self):
        if not pyperclip: return False,"❌ Нужен pyperclip."
        try: return True,pyperclip.paste() or "(буфер пуст)"
        except Exception as e: return False,f"❌ {e}"

    def clip_set(self,text):
        if not pyperclip: return False,"❌ Нужен pyperclip."
        try: pyperclip.copy(text); return True,"✅ Буфер обмена обновлён."
        except Exception as e: return False,f"❌ {e}"

    def hotkey(self,name):
        keys=self.allowed_hotkeys.get(name)
        if not keys: return False,"⛔ Комбинация не входит в allow-list."
        if not pyautogui: return False,"❌ Нужен pyautogui."
        try: pyautogui.hotkey(*keys); return True,f"⌨️ {name} выполнено."
        except Exception as e: return False,f"❌ {e}"

    def projects(self):
        return "📦 ПРОЕКТЫ\n" + ("\n".join(f"• {n}" for n in self.allowed_projects) or "нет")

    def run_project(self,name):
        path=self.allowed_projects.get(name)
        if not path: return False,"⛔ Проект не входит в allow-list."
        try:
            subprocess.Popen([os.environ.get("PYTHON","python"),str(path)],cwd=str(path.parent),creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0))
            return True,f"✅ Проект {name} запущен."
        except Exception as e: return False,f"❌ {e}"

    def drives(self):
        if not psutil: return "❌ Нужен psutil."
        return "💽 ДИСКИ\n" + "\n".join(f"• {p.device} {p.fstype} | {self._gb(psutil.disk_usage(p.mountpoint).used)} / {self._gb(psutil.disk_usage(p.mountpoint).total)} GB" for p in psutil.disk_partitions(all=False))

    def network(self):
        if not psutil: return "❌ Нужен psutil."
        io=psutil.net_io_counters(); return f"🌐 СЕТЬ\n↑ Отправлено: {io.bytes_sent/1024/1024:.1f} MB\n↓ Получено: {io.bytes_recv/1024/1024:.1f} MB\nИнтерфейсы: {', '.join(psutil.net_if_addrs())}"

    def services(self):
        if win32serviceutil is None: return "❌ Нужен pywin32."
        lines=["⚙️ СЛУЖБЫ (ALLOW-LIST)"]
        for key,svc in self.allowed_services.items():
            try: state=win32serviceutil.QueryServiceStatus(svc)[1]
            except Exception as e: state=f"error: {e}"
            lines.append(f"• {key}: {state}")
        return "\n".join(lines)

    def service_action(self,name,action):
        if name not in self.allowed_services or win32serviceutil is None: return False,"⛔ Служба не входит в allow-list или pywin32 отсутствует."
        try:
            (win32serviceutil.StartService if action=="start" else win32serviceutil.StopService)(self.allowed_services[name])
            return True,f"✅ {action} {name} выполнено."
        except Exception as e: return False,f"❌ {e}"
