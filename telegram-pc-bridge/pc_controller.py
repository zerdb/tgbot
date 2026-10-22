import ctypes
import getpass
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import zipfile
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
    from screeninfo import get_monitors
except ImportError:
    get_monitors = None

try:
    import win32gui
    import win32con
    import win32process
    import win32serviceutil
except ImportError:
    win32gui = win32con = win32process = win32serviceutil = None

STARTED_AT = time.time()


class PCController:
    """Safe local PC control with explicit allow-lists and path boundaries."""

    def __init__(self):
        home = Path.home()
        self.psutil = psutil
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
            "ctrl_a": ("ctrl", "a"),
            "ctrl_f": ("ctrl", "f"),
        }
        self.allowed_services = {
            "spooler": "Spooler",
            "w32time": "W32Time",
            "bits": "BITS",
        }
        self.allowed_projects = self._find_projects()
        self._protected_process_names = {
            "system", "system idle process", "registry", "smss.exe", "csrss.exe",
            "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
            "dwm.exe", "svchost.exe", "explorer.exe"
        }

    def _build_apps(self):
        if os.name == "nt":
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
        return {"files": ["xdg-open", str(Path.home())]}

    def _find_projects(self):
        root = Path(__file__).resolve().parents[1]
        candidates = {
            "tkinter-file-sorter": root / "tkinter-file-sorter" / "tkinter_file_sorter.py",
            "tkinter-tetris": root / "tkinter-tetris" / "tetris.py",
            "telegram-pc-bridge": root / "telegram-pc-bridge" / "main.py",
        }
        return {name: path for name, path in candidates.items() if path.exists()}

    def help_text(self):
        return (
            "🎛 PC BRIDGE v3\n\n"
            "🖥 /status  📊 /processes  🪟 /windows\n"
            "📱 /run <app>  ⛔ /stop <app>\n"
            "📁 /files <desktop|downloads|documents>\n"
            "📸 /screenshot [full|active|monitor]\n"
            "🧠 /proc <pid>  ⛔ /kill <pid>\n"
            "🪟 /focus <title>  /close <title>\n"
            "📋 /clip_get  ✏ /clip_set <text>\n"
            "⌨ /hotkey <allow-list>  📦 /projects\n"
            "▶ /project <allow-list project>\n"
            "💽 /drives  🌐 /network  🎮 /gpu\n"
            "⚙ /services  /service_start <name>  /service_stop <name>\n"
            "🔔 /alerts_on  /alerts_off\n"
            "⏻ /shutdown  /restart  💤 /sleep\n"
            "⬆️ Telegram file → Downloads\n"
            "⚠️ Опасные действия подтверждаются в Telegram."
        )

    def execute(self, text):
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if command in ("/help", "/start"):
            return True, self.help_text()
        if command == "/status":
            return True, self.status()
        if command == "/apps":
            return True, "🧩 Приложения:\n" + "\n".join("• " + x for x in self.allowed_apps)
        if command == "/run":
            return self.run_app(arg.lower())
        if command == "/stop":
            return self.stop_allowed_app(arg.lower())
        if command == "/files":
            return self.list_files(arg or "downloads")
        if command == "/find":
            parts = arg.split(maxsplit=1)
            if len(parts) < 2:
                return False, "❌ Формат: /find downloads имя"
            found = self.search_files(parts[0], parts[1])
            if not found:
                return True, "🔎 Ничего не найдено."
            return True, "🔎 НАЙДЕНО
" + "
".join("• " + (self.relative_key(item) or item.name) for item in found)
        if command == "/rename":
            parts = arg.split(maxsplit=1)
            if len(parts) < 2:
                return False, "❌ Формат: /rename downloads/file.txt новое.txt"
            return self.rename_file(parts[0], parts[1])
        if command == "/copy":
            parts = arg.split(maxsplit=1)
            if len(parts) < 2:
                return False, "❌ Формат: /copy downloads/file.txt documents"
            return self.copy_file(parts[0], parts[1])
        if command == "/archive":
            return self.archive_file(arg)
        if command == "/stats":
            return self.path_info(arg)
        if command == "/processes":
            return True, self.processes()
        if command == "/proc":
            return self.process_info(arg)
        if command == "/kill":
            return self.kill_process(arg)
        if command == "/windows":
            return True, self.windows_list()
        if command == "/focus":
            return self.focus_window(arg)
        if command == "/close":
            return self.close_window(arg)
        if command == "/minimize_all":
            return self.minimize_all()
        if command == "/logoff":
            return self.logoff_windows()
        if command == "/lock":
            return self.lock_windows()
        if command == "/shutdown":
            return self.power_action("shutdown")
        if command == "/restart":
            return self.power_action("restart")
        if command == "/sleep":
            return self.power_action("sleep")
        if command == "/screenshot":
            return True, "SCREENSHOT:" + (arg.lower() or "full")
        if command == "/download":
            return True, "DOWNLOAD:" + arg
        if command == "/clip_get":
            return self.clip_get()
        if command == "/clip_set":
            return self.clip_set(arg)
        if command == "/hotkey":
            return self.hotkey(arg.lower())
        if command == "/click":
            parts = arg.split()
            if len(parts) != 2:
                return False, "❌ Формат: /click X Y"
            try:
                return self.mouse_click(int(parts[0]), int(parts[1]))
            except ValueError:
                return False, "❌ X и Y должны быть числами."
        if command == "/type":
            return self.type_text(arg)
        if command == "/projects":
            return True, self.projects()
        if command == "/project":
            return self.run_project(arg.lower())
        if command == "/project_log":
            return self.project_log(arg.lower())
        if command == "/drives":
            return True, self.drives()
        if command == "/network":
            return True, self.network()
        if command == "/gpu":
            return True, self.gpu_status()
        if command == "/services":
            return True, self.services()
        if command == "/service_start":
            return self.service_action(arg.lower(), "start")
        if command == "/service_stop":
            return self.service_action(arg.lower(), "stop")
        if command == "/alerts_on":
            return True, "ALERTS_ON"
        if command == "/alerts_off":
            return True, "ALERTS_OFF"
        return False, "❌ Неизвестная команда. /help"

    def status(self):
        root = Path.home().anchor or "/"
        usage = shutil.disk_usage(root)
        uptime = int(time.time() - STARTED_AT)
        cpu = psutil.cpu_percent(0.4) if psutil else 0
        mem = psutil.virtual_memory() if psutil else None
        net = psutil.net_io_counters() if psutil else None
        lines = [
            "🖥 СТАТУС ПК",
            "━━━━━━━━━━━━━━━━━━",
            "✅ Bridge: работает",
            f"👤 {getpass.getuser()}",
            f"💻 {socket.gethostname()}",
            f"🪟 {platform.system()} {platform.release()}",
            f"🐍 Python {platform.python_version()}",
            f"⚡ CPU: {cpu:.1f}%",
        ]
        if mem:
            lines.append(f"🧠 RAM: {mem.percent:.1f}% ({self._gb(mem.used)} / {self._gb(mem.total)} GB)")
        lines.extend([
            f"🌐 IP: {self._local_ip()}",
            f"⏱ Bridge: {uptime // 3600:02d}:{(uptime % 3600) // 60:02d}:{uptime % 60:02d}",
            f"💽 Диск {root}: {self._gb(usage.used)} / {self._gb(usage.total)} GB ({usage.used / usage.total * 100:.1f}%)",
            f"📦 Свободно: {self._gb(usage.free)} GB",
        ])
        if net:
            lines.append(f"🌐 Сеть: ↑ {net.bytes_sent / 1024 / 1024:.1f} MB / ↓ {net.bytes_recv / 1024 / 1024:.1f} MB")
        return "\n".join(lines)

    def dashboard(self):
        return self.status() + "\n\n" + self.gpu_status() + "\n\n" + self.drives()

    @staticmethod
    def _gb(value):
        return f"{value / (1024 ** 3):.1f}"

    def _local_ip(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "недоступен"
        finally:
            sock.close()

    def processes(self, limit=20):
        if not psutil:
            return "❌ Установите psutil."
        rows = []
        for process in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            try:
                info = process.info
                rss = info["memory_info"].rss if info["memory_info"] else 0
                rows.append((rss, info["pid"], info["name"] or "?", info["cpu_percent"] or 0))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        rows.sort(reverse=True)
        return "📊 ТОП ПРОЦЕССОВ\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(
            f"• {name} | PID {pid} | RAM {memory / 1024 / 1024:.1f} MB | CPU {cpu:.1f}%"
            for memory, pid, name, cpu in rows[:limit]
        )

    def process_info(self, raw_pid):
        if not psutil:
            return False, "❌ Нужен psutil."
        try:
            pid = int(raw_pid)
        except ValueError:
            return False, "❌ PID должен быть числом."
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                name = p.name()
                cmdline = " ".join(p.cmdline())[:500]
                mem = p.memory_info().rss / 1024 / 1024
                cpu = p.cpu_percent(0.2)
                status = p.status()
                create = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.create_time()))
            return True, (
                f"🧠 PROCESS {pid}\n━━━━━━━━━━━━━━━━━━\n"
                f"• Имя: {name}\n• Статус: {status}\n• CPU: {cpu:.1f}%\n"
                f"• RAM: {mem:.1f} MB\n• Запущен: {create}\n• Команда: {cmdline or '(скрыта)'}"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            return False, f"❌ Процесс недоступен: {exc}"

    def kill_process(self, raw_pid):
        if not psutil:
            return False, "❌ Нужен psutil."
        try:
            pid = int(raw_pid)
        except ValueError:
            return False, "❌ PID должен быть числом."
        if pid in (0, 4, os.getpid()) or pid < 5:
            return False, "⛔ Этот PID защищён."
        try:
            p = psutil.Process(pid)
            name = (p.name() or "").lower()
            if name in self._protected_process_names:
                return False, f"⛔ Процесс {name} защищён."
            p.terminate()
            return True, f"⛔ Процесс {pid} ({name}) получил команду завершения."
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            return False, f"❌ Не удалось завершить процесс: {exc}"

    def windows_list(self):
        if win32gui is None:
            return "❌ Для управления окнами нужен pywin32."
        rows = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = 0
            rows.append((hwnd, title, pid))
            return True

        win32gui.EnumWindows(callback, None)
        rows.sort(key=lambda item: item[1].lower())
        return "🪟 ОКНА\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(
            f"• {title} | PID {pid}" for _, title, pid in rows[:50]
        )

    def window_records(self, limit=30):
        if win32gui is None:
            return []
        rows = []

        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    except Exception:
                        pid = 0
                    rows.append((hwnd, title, pid))
            return True

        win32gui.EnumWindows(callback, None)
        rows.sort(key=lambda item: item[1].lower())
        return rows[:limit]

    def focus_window(self, title):
        if win32gui is None or not title:
            return False, "❌ Нужен pywin32 и точный заголовок окна."
        hwnd = win32gui.FindWindow(None, title)
        if not hwnd:
            return False, f"❌ Окно «{title}» не найдено."
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True, f"✅ Фокус переключён на «{title}»."
        except Exception as exc:
            return False, f"❌ Не удалось переключить фокус: {exc}"

    def close_window(self, title):
        if win32gui is None or not title:
            return False, "❌ Нужен pywin32 и точный заголовок окна."
        hwnd = win32gui.FindWindow(None, title)
        if not hwnd:
            return False, f"❌ Окно «{title}» не найдено."
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return True, f"✅ Окно «{title}» получило команду закрытия."
        except Exception as exc:
            return False, f"❌ Не удалось закрыть окно: {exc}"

    def minimize_window(self, hwnd):
        if win32gui is None:
            return False, "❌ Нужен pywin32."
        try:
            win32gui.ShowWindow(int(hwnd), win32con.SW_MINIMIZE)
            return True, "🖥 Окно свёрнуто."
        except Exception as exc:
            return False, f"❌ {exc}"

    def screenshot_window(self, hwnd):
        if pyautogui is None or win32gui is None:
            return None, "❌ Для скриншота окна нужны pyautogui и pywin32."
        try:
            left, top, right, bottom = win32gui.GetWindowRect(int(hwnd))
            if right <= left or bottom <= top:
                return None, "❌ Некорректный размер окна."
            path = Path(__file__).with_name("downloads") / "window.png"
            path.parent.mkdir(exist_ok=True)
            image = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
            image.save(path)
            return path, ""
        except Exception as exc:
            return None, f"❌ {exc}"

    def logoff_windows(self):
        if os.name != "nt":
            return False, "❌ Только Windows."
        try:
            if ctypes.windll.user32.ExitWindowsEx(0, 0):
                return True, "🚪 Сеанс Windows завершён."
            return False, "❌ Windows не разрешила выход."
        except Exception as exc:
            return False, f"❌ {exc}"

    def power_action(self, action):
        if os.name != "nt":
            return False, "❌ Управление питанием сейчас реализовано для Windows."
        commands = {
            "shutdown": ["shutdown", "/s", "/t", "5"],
            "restart": ["shutdown", "/r", "/t", "5"],
        }
        if action == "sleep":
            try:
                ctypes.windll.powrprof.SetSuspendState(False, True, False)
                return True, "💤 ПК переводится в сон."
            except Exception as exc:
                return False, f"❌ Не удалось перевести ПК в сон: {exc}"
        try:
            subprocess.Popen(commands[action], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"⏻ Команда {action} отправлена. Задержка Windows: 5 сек."
        except Exception as exc:
            return False, f"❌ {exc}"

    def minimize_all(self):
        if os.name != "nt":
            return False, "❌ Только Windows."
        try:
            pyautogui.hotkey("win", "d") if pyautogui else ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
            return True, "🖥 Все окна свёрнуты."
        except Exception as exc:
            return False, f"❌ {exc}"

    def lock_windows(self):
        if os.name != "nt":
            return False, "❌ Только Windows."
        try:
            return (
                (True, "🔒 ПК заблокирован.")
                if ctypes.windll.user32.LockWorkStation()
                else (False, "❌ Windows не подтвердила блокировку.")
            )
        except Exception as exc:
            return False, f"❌ {exc}"

    def screenshot(self, mode="full", monitor=0, delay=0):
        if pyautogui is None:
            return None, "❌ Нужен pyautogui. Обновите зависимости."
        try:
            if delay:
                time.sleep(min(max(int(delay), 0), 10))
            path = Path(__file__).with_name("downloads") / "screen.png"
            path.parent.mkdir(exist_ok=True)
            if mode == "active" and win32gui is not None:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    image = pyautogui.screenshot(region=(left, top, right - left, bottom - top))
                else:
                    image = pyautogui.screenshot()
            elif mode == "monitor":
                monitors = self.monitor_records()
                if not monitors:
                    image = pyautogui.screenshot()
                else:
                    monitor = max(0, min(int(monitor), len(monitors) - 1))
                    left, top, width, height = monitors[monitor]
                    image = pyautogui.screenshot(region=(left, top, width, height))
            else:
                image = pyautogui.screenshot()
            image.save(path)
            return path, ""
        except Exception as exc:
            return None, f"❌ Скриншот: {exc}"

    def monitor_records(self):
        if get_monitors is not None:
            try:
                return [(m.x, m.y, m.width, m.height) for m in get_monitors()]
            except Exception:
                pass
        if pyautogui is None:
            return []
        try:
            width, height = pyautogui.size()
            return [(0, 0, width, height)]
        except Exception:
            return []

    def clip_get(self):
        if not pyperclip:
            return False, "❌ Нужен pyperclip."
        try:
            value = pyperclip.paste() or "(буфер пуст)"
            return True, value[:4000]
        except Exception as exc:
            return False, f"❌ {exc}"

    def clip_set(self, text):
        if not pyperclip:
            return False, "❌ Нужен pyperclip."
        if len(text) > 4000:
            return False, "❌ Текст ограничен 4000 символами."
        try:
            pyperclip.copy(text)
            return True, "✅ Буфер обмена обновлён."
        except Exception as exc:
            return False, f"❌ {exc}"

    def mouse_click(self, x, y):
        if pyautogui is None:
            return False, "❌ Нужен pyautogui."
        try:
            width, height = pyautogui.size()
            if not (0 <= x < width and 0 <= y < height):
                return False, f"❌ Координаты вне основного экрана: {width}x{height}."
            pyautogui.click(x, y)
            return True, f"🖱 Клик: {x}, {y}"
        except Exception as exc:
            return False, f"❌ {exc}"

    def type_text(self, text):
        if pyautogui is None:
            return False, "❌ Нужен pyautogui."
        if not text:
            return False, "❌ Текст пуст."
        if len(text) > 1000:
            return False, "❌ Ввод ограничен 1000 символами."
        try:
            pyautogui.write(text, interval=0.01)
            return True, "⌨️ Текст введён."
        except Exception as exc:
            return False, f"❌ {exc}"

    def hotkey(self, name):
        keys = self.allowed_hotkeys.get(name)
        if not keys:
            return False, "⛔ Комбинация не входит в allow-list."
        if not pyautogui:
            return False, "❌ Нужен pyautogui."
        try:
            pyautogui.hotkey(*keys)
            return True, f"⌨️ {name} выполнено."
        except Exception as exc:
            return False, f"❌ {exc}"

    def projects(self):
        return "📦 ПРОЕКТЫ\n" + ("\n".join(f"• {name}" for name in self.allowed_projects) or "нет")

    def run_project(self, name):
        path = self.allowed_projects.get(name)
        if not path:
            return False, "⛔ Проект не входит в allow-list."
        try:
            log_dir = Path(__file__).with_name("project_logs")
            log_dir.mkdir(exist_ok=True)
            log_path = log_dir / f"{name}.log"
            log = log_path.open("a", encoding="utf-8")
            log.write("\n\n===== START " + time.strftime("%Y-%m-%d %H:%M:%S") + " =====\n")
            log.flush()
            subprocess.Popen(
                [sys.executable, str(path)],
                cwd=str(path.parent),
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            return True, f"✅ Проект {name} запущен. Лог: project_logs/{name}.log"
        except Exception as exc:
            return False, f"❌ {exc}"

    def project_log(self, name, lines=40):
        if name not in self.allowed_projects:
            return False, "⛔ Проект не входит в allow-list."
        path = Path(__file__).with_name("project_logs") / f"{name}.log"
        if not path.exists():
            return False, "📋 Лог проекта пока пуст."
        try:
            data = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return True, f"📋 ЛОГ {name}\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(data[-lines:])
        except OSError as exc:
            return False, f"❌ {exc}"

    def drives(self):
        if not psutil:
            return "❌ Нужен psutil."
        rows = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                rows.append(
                    f"• {part.device} {part.fstype or '-'} | "
                    f"{self._gb(usage.used)} / {self._gb(usage.total)} GB "
                    f"({usage.percent:.1f}%)"
                )
            except OSError:
                pass
        return "💽 ДИСКИ\n" + ("\n".join(rows) or "нет доступных дисков")

    def network(self):
        if not psutil:
            return "❌ Нужен psutil."
        io = psutil.net_io_counters()
        interfaces = ", ".join(psutil.net_if_addrs()) or "нет"
        return (
            "🌐 СЕТЬ\n"
            f"↑ Отправлено: {io.bytes_sent / 1024 / 1024:.1f} MB\n"
            f"↓ Получено: {io.bytes_recv / 1024 / 1024:.1f} MB\n"
            f"Интерфейсы: {interfaces}"
        )

    def gpu_status(self):
        if os.name != "nt":
            return "ℹ️ GPU: nvidia-smi доступен только в Windows."
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return "🎮 GPU\n" + "\n".join("• " + line for line in lines) if lines else "ℹ️ NVIDIA GPU не обнаружен."
        except Exception:
            return "ℹ️ NVIDIA GPU не обнаружен или nvidia-smi недоступен."

    def services(self):
        if win32serviceutil is None:
            return "❌ Нужен pywin32."
        lines = ["⚙️ СЛУЖБЫ (ALLOW-LIST)"]
        for key, service in self.allowed_services.items():
            try:
                state = win32serviceutil.QueryServiceStatus(service)[1]
            except Exception as exc:
                state = f"error: {exc}"
            lines.append(f"• {key}: {state}")
        return "\n".join(lines)

    def service_action(self, name, action):
        if name not in self.allowed_services or win32serviceutil is None:
            return False, "⛔ Служба не входит в allow-list или pywin32 отсутствует."
        try:
            method = win32serviceutil.StartService if action == "start" else win32serviceutil.StopService
            method(self.allowed_services[name])
            return True, f"✅ {action} {name} выполнено."
        except Exception as exc:
            return False, f"❌ {exc}"

    def run_app(self, name):
        command = self.allowed_apps.get(name)
        if not command:
            return False, "⛔ Приложение не входит в allow-list."
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"✅ {name} запущено."
        except Exception as exc:
            return False, f"❌ {exc}"

    def stop_allowed_app(self, name):
        if not psutil or name not in self.allowed_apps:
            return False, "⛔ Приложение не входит в allow-list."
        targets = {
            "notepad": {"notepad.exe"},
            "calculator": {"calc.exe", "calculatorapp.exe"},
            "explorer": {"explorer.exe"},
        }.get(name, set())
        count = 0
        for process in psutil.process_iter(["name"]):
            try:
                if (process.info["name"] or "").lower() in targets:
                    process.terminate()
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return (
            (True, f"✅ {name}: остановлено {count}.")
            if count
            else (False, f"ℹ️ {name} не запущено.")
        )

    def _folder(self, name):
        folder = self.allowed_folders.get(name.lower())
        return folder.resolve() if folder else None

    def resolve_allowed_path(self, raw, must_exist=False, allow_root=False):
        raw = raw.strip().replace("\\", "/")
        if not raw:
            return None
        path = Path(raw)
        if path.is_absolute() or not path.parts:
            return None
        folder = self._folder(path.parts[0])
        if folder is None:
            return None
        target = (folder.joinpath(*path.parts[1:])).resolve()
        try:
            target.relative_to(folder)
        except ValueError:
            return None
        if not allow_root and target == folder:
            return None
        if must_exist and not target.exists():
            return None
        return target

    def resolve_allowed_file(self, raw):
        target = self.resolve_allowed_path(raw, must_exist=True)
        return target if target and target.is_file() else None

    def download_path(self, raw):
        target = self.resolve_allowed_file(raw)
        if not target:
            return False, "❌ Нужен существующий файл в Desktop, Downloads или Documents."
        return True, str(target)

    def relative_key(self, path):
        resolved = Path(path).resolve()
        for name, folder in self.allowed_folders.items():
            root = folder.resolve()
            try:
                return f"{name}/{resolved.relative_to(root).as_posix()}"
            except ValueError:
                continue
        return None

    def list_files(self, key):
        folder = self._folder(key.split("/", 1)[0])
        target = self.resolve_allowed_path(key, must_exist=True, allow_root=True)
        if not folder or not target or not target.is_dir():
            return False, "⛔ Папка не разрешена или не найдена."
        try:
            items = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            lines = [f"📂 {self.relative_key(target)}", f"Объектов: {len(items)}", ""]
            for item in items[:100]:
                prefix = "📁" if item.is_dir() else "📄"
                size = ""
                if item.is_file():
                    try:
                        size = f" • {self._size(item.stat().st_size)}"
                    except OSError:
                        pass
                lines.append(f"{prefix} {item.name}{size}")
            if len(items) > 100:
                lines.append(f"… ещё {len(items) - 100}")
            return True, "\n".join(lines)
        except OSError as exc:
            return False, f"❌ {exc}"

    @staticmethod
    def _size(value):
        units = ("B", "KB", "MB", "GB", "TB")
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{value} B"

    def search_files(self, key, query, limit=50):
        target = self.resolve_allowed_path(key, must_exist=True, allow_root=True)
        if not target or not target.is_dir():
            return []
        query = query.lower().strip()
        if not query:
            return []
        found = []
        try:
            for item in target.rglob("*"):
                if query in item.name.lower():
                    found.append(item)
                    if len(found) >= limit:
                        break
        except OSError:
            pass
        return found

    def rename_file(self, raw, new_name):
        source = self.resolve_allowed_path(raw, must_exist=True)
        if not source or not new_name.strip():
            return False, "❌ Файл/папка не найдены."
        if Path(new_name).name != new_name:
            return False, "❌ Новое имя должно быть одним именем без пути."
        target = source.with_name(new_name.strip())
        root = self._folder(raw.split("/", 1)[0])
        try:
            target.resolve().relative_to(root)
        except ValueError:
            return False, "❌ Недопустимый путь."
        if target.exists():
            return False, "❌ Объект с таким именем уже существует."
        try:
            source.rename(target)
            return True, f"✅ Переименовано: {target.name}"
        except OSError as exc:
            return False, f"❌ {exc}"

    def delete_file(self, raw):
        target = self.resolve_allowed_path(raw, must_exist=True)
        if not target:
            return False, "❌ Объект не найден или путь запрещён."
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return True, f"🗑 Удалено: {target.name}"
        except OSError as exc:
            return False, f"❌ {exc}"

    def copy_file(self, source_raw, dest_raw):
        source = self.resolve_allowed_path(source_raw, must_exist=True)
        destination = self.resolve_allowed_path(dest_raw, allow_root=True)
        if not source or not destination:
            return False, "❌ Источник или папка назначения запрещены."
        if not destination.is_dir():
            return False, "❌ Назначение должно быть папкой."
        target = destination / source.name
        if target.exists():
            return False, "❌ Такой объект уже существует."
        try:
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            return True, f"📋 Скопировано в {self.relative_key(destination)}."
        except OSError as exc:
            return False, f"❌ {exc}"

    def archive_file(self, raw):
        source = self.resolve_allowed_path(raw, must_exist=True)
        if not source:
            return False, "❌ Объект не найден."
        archive = source.with_name(source.name + ".zip")
        if archive.exists():
            return False, "❌ Архив уже существует."
        try:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                if source.is_dir():
                    for item in source.rglob("*"):
                        if item.is_file():
                            zf.write(item, item.relative_to(source.parent))
                else:
                    zf.write(source, source.name)
            return True, f"📦 Архив создан: {archive.name}"
        except OSError as exc:
            return False, f"❌ {exc}"

    def folder_stats(self, key):
        target = self.resolve_allowed_path(key, must_exist=True, allow_root=True)
        if not target or not target.is_dir():
            return False, "❌ Папка не найдена."
        count = 0
        size = 0
        try:
            for item in target.rglob("*"):
                if item.is_file():
                    count += 1
                    try:
                        size += item.stat().st_size
                    except OSError:
                        pass
            return True, f"📊 {self.relative_key(target)}\nФайлов: {count}\nРазмер: {self._size(size)}"
        except OSError as exc:
            return False, f"❌ {exc}"

    def receive_upload_path(self, filename):
        safe_name = Path(filename).name
        if not safe_name or safe_name in (".", ".."):
            safe_name = "upload.bin"
        destination = self.allowed_folders["downloads"] / safe_name
        if destination.exists():
            stem, suffix = destination.stem, destination.suffix
            index = 2
            while destination.exists():
                destination = self.allowed_folders["downloads"] / f"{stem} ({index}){suffix}"
                index += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def audit_summary(self, audit_file, limit=20):
        if not audit_file.exists():
            return "📋 Журнал пуст."
        try:
            lines = audit_file.read_text(encoding="utf-8", errors="replace").splitlines()
            return "📋 ПОСЛЕДНИЕ ДЕЙСТВИЯ\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(lines[-limit:])
        except OSError as exc:
            return f"❌ {exc}"
