import argparse
import base64
import mimetypes
import os
import re
import time
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
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
                    ".svg", ".avif", ".tif", ".tiff", ".ico"}


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
        total=3, connect=3, read=3, backoff_factor=1,
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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
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
    return content_type.startswith("image/") or "octet-stream" in content_type or ext in IMAGE_EXTENSIONS


def download_one(session, url, save_path, index, referer):
    candidates = [upgrade_url(url)]
    if candidates[0] != url:
        candidates.append(url)
    last_error = None

    for candidate in candidates:
        try:
            response = session.get(
                candidate, timeout=(5, 30), stream=True,
                headers={"Referer": referer},
            )
            response.raise_for_status()
            if not is_image_response(response, candidate):
                response.close()
                continue

            path = unique_path(os.path.join(
                save_path, safe_filename(candidate, index, response.headers.get("Content-Type", ""))
            ))
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

    result, seen = [], set()
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


def parse_args():
    parser = argparse.ArgumentParser(description="Скачивание изображений со страницы")
    parser.add_argument("url", nargs="?", default=PAGE_URL)
    parser.add_argument("--output", default=SAVE_DIR)
    parser.add_argument("--limit", type=int, default=MAX_IMAGES,
                        help="0 = без лимита")
    parser.add_argument("--delay", type=float, default=DELAY)
    parser.add_argument("--no-html", action="store_true")
    parser.add_argument("--no-upgrade", action="store_true")
    return parser.parse_args()


def download_images():
    args = parse_args()
    page_url = args.url
    parsed = urlparse(page_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Некорректный URL: {page_url}")

    global UPGRADE_URLS
    old_upgrade = UPGRADE_URLS
    UPGRADE_URLS = not args.no_upgrade

    max_images = None if args.limit == 0 else max(args.limit, 0)
    delay = max(args.delay, 0)
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    save_path = os.path.join(args.output, site_folder_name(page_url))
    os.makedirs(save_path, exist_ok=True)
    session = build_session(page_url)

    try:
        print(f"🌐 Загружаем страницу: {page_url}")
        response = session.get(page_url, timeout=(10, 30))
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        html = response.text
        print(f"✅ HTML получен: {len(html)} символов")

        if SAVE_HTML and not args.no_html:
            with open(os.path.join(save_path, "page.html"), "w", encoding="utf-8") as file:
                file.write(html)

        soup = BeautifulSoup(html, "html.parser")
        urls = collect_urls(soup, base_url)
        print(f"🔍 Найдено уникальных источников: {len(urls)}")
        print(f"📂 Папка: {save_path}")
        print(f"🎯 Лимит: {max_images if max_images is not None else '∞'}")

        downloaded = failed = 0
        for index, raw_url in enumerate(urls, 1):
            if max_images is not None and downloaded >= max_images:
                break

            if raw_url.startswith("data:"):
                filename, size = save_base64(raw_url, save_path, index)
                if filename:
                    downloaded += 1
                    print(f"✅ [{downloaded}/{max_images or '∞'}] {filename} ({size // 1024} КБ)")
                else:
                    failed += 1
                continue

            try:
                filename, size = download_one(session, raw_url, save_path, index, page_url)
                if filename:
                    downloaded += 1
                    print(f"✅ [{downloaded}/{max_images or '∞'}] {filename} ({size // 1024} КБ)")
                else:
                    failed += 1
            except (requests.RequestException, OSError) as error:
                failed += 1
                print(f"⚠️ {raw_url[:100]}... → {type(error).__name__}: {error}")

            if delay:
                time.sleep(delay)

        files = [
            name for name in os.listdir(save_path)
            if os.path.isfile(os.path.join(save_path, name))
            and not name.lower().endswith((".html", ".htm", ".txt"))
            and os.path.getsize(os.path.join(save_path, name)) > 0
        ]
        print("\n📊 Итог:")
        print(f"   ✅ Новых скачано: {downloaded}")
        print(f"   ⚠️ Ошибок: {failed}")
        print(f"   📦 Всего файлов: {len(files)}")
        print(f"   📂 {os.path.abspath(save_path)}")
    finally:
        UPGRADE_URLS = old_upgrade
        session.close()


if __name__ == "__main__":
    download_images()
