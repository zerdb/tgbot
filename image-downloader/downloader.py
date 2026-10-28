import argparse
import base64
import mimetypes
import os
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


PAGE_URL = "https://smtp.bz/"
SAVE_DIR = "downloaded_images"
SAVE_HTML = True
USE_PROXY = False
UPGRADE_URLS = True
DELAY = 0.3
MAX_IMAGES = 10000

SRC_PRIORITY = [
    "data-full", "data-original", "data-large", "data-hi-res",
    "data-src", "data-lazy-src", "data-image", "data-original-src",
    "srcset", "data-srcset", "src",
]
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".svg", ".avif", ".tif", ".tiff", ".ico",
}


def pick_best_url(tag):
    for attr in SRC_PRIORITY:
        value = tag.get(attr)
        if not value:
            continue
        if attr in {"srcset", "data-srcset"}:
            candidates = []
            for item in value.split(","):
                parts = item.strip().split()
                if not parts:
                    continue
                width = 0
                if len(parts) > 1:
                    match = re.fullmatch(r"(\d+)w", parts[1])
                    if match:
                        width = int(match.group(1))
                candidates.append((width, parts[0]))
            if candidates:
                return max(candidates, key=lambda x: x[0])[1]
            continue
        return value.strip()
    return None


def extract_picture_urls(soup):
    urls = []
    for source in soup.find_all("source"):
        for attr in ("srcset", "data-srcset", "data-src", "src"):
            value = source.get(attr)
            if not value:
                continue
            if attr in {"srcset", "data-srcset"}:
                parts = [p.strip().split() for p in value.split(",") if p.strip()]
                if parts:
                    urls.append(parts[-1][0])
            else:
                urls.append(value.strip())
            break
    return urls


def extract_css_urls(soup):
    pattern = re.compile(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", re.I)
    urls = []
    for tag in soup.find_all(style=True):
        urls.extend(m.group(1).strip() for m in pattern.finditer(tag["style"]))
    for style in soup.find_all("style"):
        urls.extend(m.group(1).strip() for m in pattern.finditer(style.get_text()))
    return urls


def upgrade_url(url):
    if not UPGRADE_URLS:
        return url
    parts = urlsplit(url)
    query = re.sub(r"[?&](w|h|width|height|size|resize)=\d+", "", parts.query)
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    replacements = [
        (r"/thumb(s)?/", "/"), (r"/small/", "/"), (r"/preview/", "/"),
        (r"/\d+x\d+/", "/"), (r"/\d+/\d+/", "/"),
        (r"_(thumb|small|mini|preview)(\.[a-z]+)$", r"\2"),
        (r"-thumb(\.[a-z]+)$", r"\1"),
        (r"-small(\.[a-z]+)$", r"\1"),
        (r"-preview(\.[a-z]+)$", r"\1"),
    ]
    for pattern, replacement in replacements:
        upgraded = re.sub(pattern, replacement, url, flags=re.I)
        if upgraded != url:
            return upgraded
    return url


def safe_filename(url, index, content_type=""):
    name = os.path.basename(urlparse(url).path).split("?")[0]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    base, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in IMAGE_EXTENSIONS:
        ext = mimetypes.guess_extension(content_type.split(";", 1)[0].lower()) or ""
        if ext == ".jpe":
            ext = ".jpg"
        if ext not in IMAGE_EXTENSIONS:
            ext = ".jpg"
    base = (base or f"image_{index}")[:100]
    return f"{base}{ext}"


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def build_session(referer):
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    })
    if not USE_PROXY:
        session.trust_env = False
    return session


def save_base64(data_uri, save_path, index):
    try:
        header, encoded = data_uri.split(",", 1)
        match = re.search(r"data:image/([\w.+-]+)", header, re.I)
        ext = "." + (match.group(1).lower() if match else "png")
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in IMAGE_EXTENSIONS:
            ext = ".png"
        raw = base64.b64decode(encoded, validate=False)
        if not raw:
            return None, 0
        path = unique_path(os.path.join(save_path, f"embedded_{index}{ext}"))
        with open(path, "wb") as file:
            file.write(raw)
        return os.path.basename(path), len(raw)
    except (ValueError, OSError):
        return None, 0


def is_image_response(response, url):
    content_type = response.headers.get("Content-Type", "").lower()
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return (
        content_type.startswith("image/")
        or "octet-stream" in content_type
        or ext in IMAGE_EXTENSIONS
    )


def download_one(session, url, save_path, index, referer):
    candidates = [upgrade_url(url)]
    if candidates[0] != url:
        candidates.append(url)

    last_error = None

    for candidate in candidates:
        try:
            response = session.get(
                candidate,
                timeout=(5, 30),
                stream=True,
                headers={"Referer": referer},
            )
            response.raise_for_status()

            if not is_image_response(response, candidate):
                response.close()
                continue

            path = unique_path(
                os.path.join(
                    save_path,
                    safe_filename(
                        candidate,
                        index,
                        response.headers.get("Content-Type", ""),
                    ),
                )
            )

            size = 0
            with open(path, "wb") as file:
                for chunk in response.iter_content(16384):
                    if chunk:
                        file.write(chunk)
                        size += len(chunk)
            response.close()

            if size == 0:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue

            return os.path.basename(path), size

        except (requests.RequestException, OSError) as error:
            last_error = error

    if last_error:
        raise last_error
    return None, 0


def collect_urls(soup, base_url):
    raw_urls = []

    for img in soup.find_all("img"):
        raw = pick_best_url(img)
        if raw:
            raw_urls.append(raw)

    raw_urls.extend(extract_picture_urls(soup))
    raw_urls.extend(extract_css_urls(soup))

    result = []
    seen = set()

    for raw in raw_urls:
        if raw.startswith("data:"):
            key = raw
        else:
            full = urljoin(base_url, raw)
            if urlparse(full).scheme not in {"http", "https"}:
                continue
            key = full

        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


def site_folder_name(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    host = re.sub(r"[^\w.-]", "_", host)
    return host or "unknown_site"


def download_images(
    page_url,
    output_dir,
    limit=MAX_IMAGES,
    delay=DELAY,
    save_html=True,
    no_upgrade=False,
    log=None,
    progress=None,
):
    parsed = urlparse(page_url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Некорректный URL: {page_url}")

    global UPGRADE_URLS
    old_upgrade = UPGRADE_URLS
    UPGRADE_URLS = not no_upgrade

    max_images = None if limit == 0 else max(limit, 0)
    delay = max(delay, 0)
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    save_path = os.path.join(output_dir, site_folder_name(page_url))
    os.makedirs(save_path, exist_ok=True)

    session = build_session(page_url)

    def write_log(text):
        if log:
            log(text)

    try:
        write_log(f"🌐 Загружаем страницу: {page_url}")
        response = session.get(page_url, timeout=(10, 30))
        response.raise_for_status()

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"

        html = response.text
        write_log(f"✅ HTML получен: {len(html)} символов")

        if save_html:
            with open(
                os.path.join(save_path, "page.html"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write(html)

        soup = BeautifulSoup(html, "html.parser")
        urls = collect_urls(soup, base_url)

        if max_images is not None:
            urls = urls[:max_images]

        total = len(urls)
        write_log(f"🔍 Найдено уникальных источников: {total}")
        write_log(f"📂 Папка: {os.path.abspath(save_path)}")

        downloaded = 0
        failed = 0

        for index, raw_url in enumerate(urls, 1):
            try:
                if raw_url.startswith("data:"):
                    filename, size = save_base64(raw_url, save_path, index)
                else:
                    filename, size = download_one(
                        session,
                        raw_url,
                        save_path,
                        index,
                        page_url,
                    )

                if filename:
                    downloaded += 1
                    write_log(
                        f"✅ [{index}/{total}] {filename} "
                        f"({size // 1024} КБ)"
                    )
                else:
                    failed += 1
                    write_log(f"⚠️ [{index}/{total}] Не удалось скачать")

            except (requests.RequestException, OSError) as error:
                failed += 1
                write_log(
                    f"⚠️ [{index}/{total}] "
                    f"{type(error).__name__}: {error}"
                )

            if progress:
                progress(index, total)

            if delay:
                time.sleep(delay)

        write_log("")
        write_log("📊 Итог:")
        write_log(f"   ✅ Скачано: {downloaded}")
        write_log(f"   ⚠️ Ошибок: {failed}")
        write_log(f"   📂 {os.path.abspath(save_path)}")

        return downloaded, failed, save_path

    finally:
        UPGRADE_URLS = old_upgrade
        session.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Скачивание изображений со страницы"
    )
    parser.add_argument("url", nargs="?", default=PAGE_URL)
    parser.add_argument("--output", default=SAVE_DIR)
    parser.add_argument("--limit", type=int, default=MAX_IMAGES)
    parser.add_argument("--delay", type=float, default=DELAY)
    parser.add_argument("--no-html", action="store_true")
    parser.add_argument("--no-upgrade", action="store_true")
    return parser.parse_args()


class ImageDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TGBOT • Image Downloader")
        self.root.geometry("760x620")
        self.root.minsize(680, 520)
        self.root.configure(bg="#111827")
        self.running = False

        self.url_var = tk.StringVar(value=PAGE_URL)
        self.output_var = tk.StringVar(
            value=str(Path.cwd() / SAVE_DIR)
        )
        self.limit_var = tk.StringVar(value=str(MAX_IMAGES))
        self.delay_var = tk.StringVar(value=str(DELAY))
        self.status_var = tk.StringVar(value="Готово к скачиванию")

        self.build_ui()

    def build_ui(self):
        header = tk.Frame(self.root, bg="#111827")
        header.pack(fill="x", padx=28, pady=(24, 14))

        tk.Label(
            header,
            text="IMAGE DOWNLOADER",
            font=("Segoe UI", 22, "bold"),
            fg="white",
            bg="#111827",
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Скачать изображения со страницы",
            font=("Segoe UI", 10),
            fg="#9ca3af",
            bg="#111827",
        ).pack(anchor="w", pady=(2, 0))

        card = tk.Frame(self.root, bg="#1f2937")
        card.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        fields = tk.Frame(card, bg="#1f2937")
        fields.pack(fill="x", padx=22, pady=(20, 10))

        self.add_entry(fields, "URL страницы", self.url_var, 0)

        output_row = tk.Frame(fields, bg="#1f2937")
        output_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        output_row.columnconfigure(1, weight=1)

        tk.Label(
            output_row,
            text="Папка",
            width=14,
            anchor="w",
            fg="#d1d5db",
            bg="#1f2937",
            font=("Segoe UI", 10),
        ).grid(row=0, column=0)

        tk.Entry(
            output_row,
            textvariable=self.output_var,
            font=("Segoe UI", 10),
            bg="#374151",
            fg="white",
            insertbackground="white",
            relief="flat",
        ).grid(row=0, column=1, sticky="ew", padx=8)

        tk.Button(
            output_row,
            text="Обзор",
            command=self.choose_folder,
            font=("Segoe UI", 9),
            fg="white",
            bg="#4b5563",
            activebackground="#6b7280",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=12,
        ).grid(row=0, column=2)

        options = tk.Frame(fields, bg="#1f2937")
        options.grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 0))

        self.add_small_entry(options, "Лимит", self.limit_var, 0)
        self.add_small_entry(options, "Задержка", self.delay_var, 1)

        tk.Label(
            options,
            text="0 = без лимита",
            fg="#9ca3af",
            bg="#1f2937",
            font=("Segoe UI", 9),
        ).grid(row=0, column=4, padx=(8, 0))

        fields.columnconfigure(1, weight=1)

        actions = tk.Frame(card, bg="#1f2937")
        actions.pack(fill="x", padx=22, pady=(4, 12))

        self.start_button = tk.Button(
            actions,
            text="⬇  Скачать изображения",
            command=self.start_download,
            font=("Segoe UI", 10, "bold"),
            fg="white",
            bg="#2563eb",
            activebackground="#3b82f6",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=18,
            pady=8,
        )
        self.start_button.pack(side="left")

        tk.Button(
            actions,
            text="Очистить лог",
            command=self.clear_log,
            font=("Segoe UI", 9),
            fg="white",
            bg="#374151",
            activebackground="#4b5563",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=8,
        ).pack(side="left", padx=8)

        self.progress = ttk.Progressbar(
            actions,
            mode="determinate",
            length=220,
        )
        self.progress.pack(side="right", padx=(10, 0))

        log_frame = tk.Frame(card, bg="#111827")
        log_frame.pack(fill="both", expand=True, padx=22, pady=(0, 14))

        self.log = tk.Text(
            log_frame,
            bg="#111827",
            fg="#d1d5db",
            insertbackground="white",
            relief="flat",
            bd=0,
            font=("Consolas", 9),
            wrap="word",
            padx=12,
            pady=10,
        )
        log_scroll = tk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log.yview,
        )
        self.log.configure(yscrollcommand=log_scroll.set)

        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            fg="#6b7280",
            bg="#111827",
        ).pack(pady=(0, 12))

    def add_entry(self, parent, label, variable, row):
        parent.columnconfigure(1, weight=1)

        tk.Label(
            parent,
            text=label,
            width=14,
            anchor="w",
            fg="#d1d5db",
            bg="#1f2937",
            font=("Segoe UI", 10),
        ).grid(row=row, column=0, sticky="w")

        tk.Entry(
            parent,
            textvariable=variable,
            font=("Segoe UI", 10),
            bg="#374151",
            fg="white",
            insertbackground="white",
            relief="flat",
        ).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))

    def add_small_entry(self, parent, label, variable, column):
        tk.Label(
            parent,
            text=label,
            fg="#d1d5db",
            bg="#1f2937",
            font=("Segoe UI", 9),
        ).grid(row=0, column=column * 2)

        tk.Entry(
            parent,
            textvariable=variable,
            width=9,
            font=("Segoe UI", 9),
            bg="#374151",
            fg="white",
            insertbackground="white",
            relief="flat",
        ).grid(row=0, column=column * 2 + 1, padx=(5, 12))

    def choose_folder(self):
        folder = filedialog.askdirectory(
            title="Выберите папку для скачивания"
        )
        if folder:
            self.output_var.set(folder)

    def append_log(self, text):
        self.root.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def update_progress(self, current, total):
        self.root.after(
            0,
            lambda: self.progress.configure(
                maximum=max(total, 1),
                value=current,
            ),
        )

    def clear_log(self):
        self.log.delete("1.0", "end")

    def start_download(self):
        if self.running:
            return

        url = self.url_var.get().strip()
        output = self.output_var.get().strip()

        try:
            limit = int(self.limit_var.get())
            delay = float(self.delay_var.get())
            if limit < 0 or delay < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Ошибка",
                "Лимит должен быть целым числом >= 0, "
                "задержка — числом >= 0.",
            )
            return

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            messagebox.showerror(
                "Ошибка",
                "Введите корректный URL, например https://example.com",
            )
            return

        if not output:
            messagebox.showerror("Ошибка", "Выберите папку для сохранения.")
            return

        self.running = True
        self.start_button.configure(
            text="⏳  Скачивание...",
            state="disabled",
        )
        self.progress.configure(value=0, maximum=1)
        self.status_var.set("Загрузка страницы...")

        worker = threading.Thread(
            target=self.run_worker,
            args=(url, output, limit, delay),
            daemon=True,
        )
        worker.start()

    def run_worker(self, url, output, limit, delay):
        try:
            downloaded, failed, save_path = download_images(
                page_url=url,
                output_dir=output,
                limit=limit,
                delay=delay,
                log=self.append_log,
                progress=self.update_progress,
            )
            self.root.after(
                0,
                lambda: self.finish(
                    f"Готово: скачано {downloaded}, ошибок {failed}\n"
                    f"Папка: {os.path.abspath(save_path)}"
                ),
            )
        except Exception as error:
            self.append_log(f"❌ Критическая ошибка: {type(error).__name__}: {error}")
            self.root.after(
                0,
                lambda: self.finish("Ошибка скачивания"),
            )

    def finish(self, status):
        self.running = False
        self.start_button.configure(
            text="⬇  Скачать изображения",
            state="normal",
        )
        self.status_var.set(status)


def run_cli():
    args = parse_args()
    download_images(
        page_url=args.url,
        output_dir=args.output,
        limit=args.limit,
        delay=args.delay,
        save_html=not args.no_html,
        no_upgrade=args.no_upgrade,
        log=print,
    )


if __name__ == "__main__":
    # Без аргументов запускаем удобное Tkinter-окно.
    # Аргументы сохраняют старый CLI-режим.
    if len(sys.argv) == 1:
        root = tk.Tk()
        ImageDownloaderApp(root)
        root.mainloop()
    else:
        run_cli()
