"""GigaAM Fleet Admin agent for Windows 10/11; telemetry only, no remote commands."""
from __future__ import annotations
import argparse, json, os, platform, socket, subprocess, time, uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

VERSION = "0.1"
APP_DIR = Path(os.environ.get("PROGRAMDATA", str(Path.home()))) / "GigaAMFleetAgent"
CONFIG_PATH = APP_DIR / "agent.json"

def ps(script):
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""

def load_config(server, token):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if server: cfg["server_url"] = server.rstrip("/")
        if token: cfg["token"] = token
    else:
        if not server or not token:
            raise SystemExit("Первый запуск: укажите --server и --token.")
        cfg = {"agent_id": str(uuid.uuid4()), "server_url": server.rstrip("/"), "token": token}
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg

def collect(agent_id):
    disks = []
    raw = ps('Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object DeviceID,Size,FreeSpace | ConvertTo-Json -Compress')
    if raw:
        try:
            items = json.loads(raw)
            if isinstance(items, dict): items = [items]
            for item in items[:20]:
                size, free = int(item.get("Size") or 0), int(item.get("FreeSpace") or 0)
                disks.append({"drive": item.get("DeviceID", ""), "size_gb": round(size / 2**30, 1),
                              "free_gb": round(free / 2**30, 1)})
        except (ValueError, TypeError):
            pass
    ram = ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
    try: ram_gb = round(int(ram) / 2**30, 1)
    except (ValueError, TypeError): ram_gb = 0.0
    return {
        "agent_id": agent_id, "agent_version": VERSION, "hostname": socket.gethostname(),
        "username": os.environ.get("USERNAME", ""),
        "mac_address": ps("(Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1 -ExpandProperty MacAddress)"),
        "os_name": ps("(Get-CimInstance Win32_OperatingSystem).Caption") or platform.system(),
        "os_version": ps("(Get-CimInstance Win32_OperatingSystem).Version") or platform.version(),
        "cpu": ps("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"),
        "ram_gb": ram_gb, "disks": disks
    }

def heartbeat(cfg):
    body = json.dumps(collect(cfg["agent_id"]), ensure_ascii=False).encode("utf-8")
    req = Request(cfg["server_url"] + "/api/v1/heartbeat", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["token"]})
    with urlopen(req, timeout=15) as response:
        response.read()
        if response.status != 200: raise RuntimeError("HTTP " + str(response.status))

def main():
    parser = argparse.ArgumentParser(description="GigaAM Fleet Admin agent")
    parser.add_argument("--server", help="Например http://192.168.1.10:8765")
    parser.add_argument("--token", help="Токен из консоли центрального сервера")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if os.name != "nt": raise SystemExit("Агент предназначен для Windows 10/11.")
    cfg = load_config(args.server, args.token)
    interval = max(15, min(args.interval, 3600))
    print(f"GigaAM agent: {socket.gethostname()}, интервал {interval} сек.")
    while True:
        try:
            heartbeat(cfg)
            print(time.strftime("%H:%M:%S") + " — данные отправлены")
        except (HTTPError, URLError, OSError, RuntimeError, ValueError) as exc:
            print(time.strftime("%H:%M:%S") + f" — ошибка связи: {exc}")
        time.sleep(interval)

if __name__ == "__main__":
    main()
