"""Loopback receiver for the companion browser extension (tab metadata only)."""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

logger = logging.getLogger("gigaam.observer.browser")


class BrowserCollector:
    def __init__(self, callback, host="127.0.0.1", port=8765):
        self.callback = callback
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_POST(self):
                if self.path != "/tabs":
                    self.send_error(404)
                    return
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 256_000)
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    browser = str(payload.get("browser", "unknown"))[:40]
                    tabs = payload.get("tabs", [])
                    if not isinstance(tabs, list):
                        raise ValueError("tabs must be a list")
                    for tab in tabs[:100]:
                        if not isinstance(tab, dict):
                            continue
                        url = str(tab.get("url", ""))[:2048]
                        title = str(tab.get("title", ""))[:300]
                        if not url.startswith(("http://", "https://")):
                            continue
                        owner.callback(
                            category="browser", event_type="tab_snapshot", source=browser,
                            object_name=title or url, object_path=url,
                            details={"active": bool(tab.get("active")), "window_id": tab.get("windowId")},
                            deduplication_key=f"browser:{browser}:{tab.get('id')}:{url}",
                        )
                    self.send_response(200)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b"ok")
                except Exception:
                    logger.exception("Invalid browser extension payload")
                    self.send_error(400)

            def log_message(self, *_args):
                return

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = Thread(target=self.server.serve_forever, name="GigaAM-Observer-Browser", daemon=True)
        self.thread.start()
        logger.info("Browser metadata receiver listening on 127.0.0.1:%s", self.server.server_port)

    def stop(self):
        if self.thread:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.thread = None
