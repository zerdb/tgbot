"""GigaAM Fleet Admin: lightweight LAN inventory server."""
from __future__ import annotations
import argparse, hmac, json, os, secrets, sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GigaAMFleetAdmin"
DB_PATH = APP_DIR / "fleet.sqlite3"
TOKEN_PATH = APP_DIR / "enrollment.token"
MAX_BODY = 65536

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def token_value():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(value, encoding="utf-8")
    return value

def db_connect():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS computers (
      agent_id TEXT PRIMARY KEY, hostname TEXT NOT NULL, username TEXT, ip_address TEXT,
      mac_address TEXT, os_name TEXT, os_version TEXT, cpu TEXT, ram_gb REAL,
      disks_json TEXT, last_seen TEXT NOT NULL, first_seen TEXT NOT NULL, agent_version TEXT NOT NULL)""")
    db.commit()
    return db

class Handler(BaseHTTPRequestHandler):
    server_version = "GigaAMFleet/0.1"
    def log_message(self, fmt, *args):
        print(f"[{now()}] {self.address_string()} {fmt % args}")
    def reply(self, status, value, content_type="application/json; charset=utf-8"):
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)
    def authorized(self):
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.token)
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self.reply(200, {"ok": True, "version": "0.1"})
        if path == "/":
            page = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GigaAM IT</title><style>
body{font:15px Segoe UI,Arial;background:#10151d;color:#e8edf5;margin:0;padding:28px}main{max-width:1200px;margin:auto}
h1{font-size:26px}.muted{color:#9aa8ba}.cards{display:flex;gap:12px;margin:22px 0}.card{background:#1b2532;padding:18px;border-radius:12px;min-width:130px}
.num{font-size:28px;font-weight:700}table{width:100%;border-collapse:collapse;background:#1b2532;border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:12px;border-bottom:1px solid #303b49}th{color:#9fb0c5}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#36c98f;margin-right:7px}.off{background:#e0a04b}
</style><main><h1>GigaAM · IT-панель</h1><div class="muted">Инвентаризация · обновление каждые 15 секунд</div>
<div style="margin:18px 0"><input id="token" type="password" placeholder="Токен из консоли сервера" style="padding:10px;width:320px;max-width:70%;background:#1b2532;color:white;border:1px solid #526174;border-radius:6px"><button id="save" style="padding:10px;margin-left:8px">Подключить</button><span id="auth" class="muted"></span></div>
<section class="cards"><div class="card">Всего ПК<div class="num" id="total">—</div></div><div class="card">В сети<div class="num" id="online">—</div></div><div class="card">Не в сети<div class="num" id="offline">—</div></div></section>
<table><thead><tr><th>Статус</th><th>Компьютер</th><th>Пользователь</th><th>IP</th><th>Windows</th><th>CPU / RAM</th><th>Последний контакт</th></tr></thead><tbody id="rows"><tr><td colspan="7">Загрузка…</td></tr></tbody></table></main>
<script>
const tokenBox=document.querySelector('#token'),authMsg=document.querySelector('#auth');
tokenBox.value=localStorage.getItem('gigaam_token')||'';
document.querySelector('#save').onclick=()=>{localStorage.setItem('gigaam_token',tokenBox.value.trim());refresh()};
async function refresh(){try{const r=await fetch('/api/v1/computers',{headers:{Authorization:'Bearer '+(localStorage.getItem('gigaam_token')||'')}});if(!r.ok)throw Error('Токен не принят (HTTP '+r.status+')');authMsg.textContent='Подключено';const a=(await r.json()).computers,on=a.filter(x=>x.online).length;
document.querySelector('#total').textContent=a.length;document.querySelector('#online').textContent=on;document.querySelector('#offline').textContent=a.length-on;
const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.querySelector('#rows').innerHTML=a.map(x=>'<tr><td><span class="dot '+(x.online?'':'off')+'"></span>'+(x.online?'В сети':'Нет связи')+'</td><td><b>'+esc(x.hostname)+'</b></td><td>'+esc(x.username)+'</td><td>'+esc(x.ip_address)+'</td><td>'+esc(x.os_name)+' '+esc(x.os_version)+'</td><td>'+esc(x.cpu)+' / '+esc(x.ram_gb)+' ГБ</td><td>'+esc(new Date(x.last_seen).toLocaleString())+'</td></tr>').join('')||'<tr><td colspan="7">Пока нет устройств</td></tr>';
 }catch(e){authMsg.textContent=e.message;document.querySelector('#rows').textContent='Введите токен сервера выше.'}}refresh();setInterval(refresh,15000);
</script></html>"""
            return self.reply(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/v1/computers":
            if not self.authorized():
                return self.reply(401, {"error": "Authorization required"})
            with db_connect() as db:
                rows = [dict(x) for x in db.execute("SELECT * FROM computers ORDER BY hostname COLLATE NOCASE")]
            for row in rows:
                row["disks"] = json.loads(row.pop("disks_json") or "[]")
                try:
                    row["online"] = (datetime.now(timezone.utc) - datetime.fromisoformat(row["last_seen"])).total_seconds() < 180
                except ValueError:
                    row["online"] = False
            return self.reply(200, {"computers": rows})
        return self.reply(404, {"error": "Not found"})
    def do_POST(self):
        if urlparse(self.path).path != "/api/v1/heartbeat":
            return self.reply(404, {"error": "Not found"})
        if not self.authorized():
            return self.reply(401, {"error": "Invalid token"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > MAX_BODY:
                return self.reply(413, {"error": "Invalid request size"})
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            for key in ("agent_id", "hostname", "agent_version"):
                if not isinstance(data.get(key), str) or not data[key].strip():
                    return self.reply(400, {"error": "Missing " + key})
            stamp = now()
            fields = {
                "agent_id": data["agent_id"][:80], "hostname": data["hostname"][:255],
                "username": str(data.get("username", ""))[:255], "ip_address": self.client_address[0],
                "mac_address": str(data.get("mac_address", ""))[:32], "os_name": str(data.get("os_name", ""))[:120],
                "os_version": str(data.get("os_version", ""))[:120], "cpu": str(data.get("cpu", ""))[:255],
                "ram_gb": float(data.get("ram_gb", 0) or 0),
                "disks_json": json.dumps(data.get("disks", [])[:20], ensure_ascii=False),
                "last_seen": stamp, "agent_version": data["agent_version"][:40]
            }
            with db_connect() as db:
                old = db.execute("SELECT first_seen FROM computers WHERE agent_id=?", (fields["agent_id"],)).fetchone()
                fields["first_seen"] = old["first_seen"] if old else stamp
                db.execute("""INSERT INTO computers VALUES (:agent_id,:hostname,:username,:ip_address,:mac_address,
                :os_name,:os_version,:cpu,:ram_gb,:disks_json,:last_seen,:first_seen,:agent_version)
                ON CONFLICT(agent_id) DO UPDATE SET hostname=excluded.hostname,username=excluded.username,
                ip_address=excluded.ip_address,mac_address=excluded.mac_address,os_name=excluded.os_name,
                os_version=excluded.os_version,cpu=excluded.cpu,ram_gb=excluded.ram_gb,disks_json=excluded.disks_json,
                last_seen=excluded.last_seen,agent_version=excluded.agent_version""", fields)
            return self.reply(200, {"ok": True, "server_time": stamp})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.reply(400, {"error": str(exc)})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    secret = token_value()
    db_connect().close()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.token = secret
    print("GigaAM Fleet Admin running")
    print(f"Dashboard: http://127.0.0.1:{args.port}/")
    print(f"Enrollment token: {secret}")
    print(f"Database: {DB_PATH}")
    print("WARNING: HTTP is unencrypted. Use only on a trusted LAN; do not expose this port to the internet.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
