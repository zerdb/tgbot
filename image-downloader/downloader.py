import os, re, time, base64, mimetypes
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= НАСТРОЙКИ =================
PAGE_URL   = "https://smtp.bz/"
SAVE_DIR   = "downloaded_images"
SAVE_HTML  = True
USE_PROXY  = False
UPGRADE_URLS = True
DELAY = 0.3
MAX_IMAGES = 10000
# =============================================

SRC_PRIORITY = [
    "data-full", "data-original", "data-large", "data-hi-res",
    "data-src", "data-lazy-src", "data-image",
    "srcset", "src",
]

def pick_best_url(img_tag):
    for attr in SRC_PRIORITY:
        val = img_tag.get(attr)
        if not val:
            continue
        if attr == "srcset":
            parts = [p.strip() for p in val.split(",") if p.strip()]
            best, best_w = None, -1
            for p in parts:
                tokens = p.split()
                if not tokens:
                    continue
                url, w = tokens[0], 0
                if len(tokens) > 1:
                    m = re.match(r"(\d+)w", tokens[1])
                    if m:
                        w = int(m.group(1))
                if w > best_w:
                    best_w, best = w, url
            if best:
                return best.strip()
            continue
        return val.strip()
    return None

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
    for pat, rep in replacements:
        new = re.sub(pat, rep, url, flags=re.IGNORECASE)
        if new != url:
            return new
    return url

def get_safe_filename(url, index):
    name = os.path.basename(urlparse(url).path).split("?")[0]
    if not name or "." not in name:
        ext = ".jpg"
        low = url.lower()
        for e in [".png", ".webp", ".gif", ".jpeg", ".bmp", ".svg"]:
            if e in low:
                ext = e
                break
        name = f"image_{index}{ext}"
    base, ext = os.path.splitext(name)
    if len(base) > 100:
        base = base[:100]
    return base + ext

def build_session(referer):
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1,
                  status_forcelist=[429, 500, 502, 503, 504])
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    })
    if not USE_PROXY:
        s.trust_env = False
    return s

def fetch_html(session, url):
    print(f"🌐 Загружаем страницу: {url}")
    r = session.get(url, timeout=(10, 30))
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    print(f"✅ HTML получен: {len(r.text)} символов")
    return r.text

def site_folder_name(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    host = re.sub(r"[^\w\.\-]", "_", host)
    return host or "unknown_site"

def save_base64_image(data_uri, save_path, index):
    """Декодирует data:image/...;base64,... и сохраняет как файл."""
    try:
        header, encoded = data_uri.split(",", 1)
        m = re.search(r"data:image/([a-zA-Z0-9.+-]+)", header)
        ext = ".png"
        if m:
            subtype = m.group(1).lower()
            if subtype == "jpeg":
                subtype = "jpg"
            ext = "." + subtype
        raw = base64.b64decode(encoded, validate=False)
        filename = f"embedded_{index}{ext}"
        filepath = os.path.join(save_path, filename)
        with open(filepath, "wb") as f:
            f.write(raw)
        return filename, len(raw)
    except Exception:
        return None, 0

def download_images():
    parsed = urlparse(PAGE_URL)
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    site_dir = site_folder_name(PAGE_URL)
    save_path = os.path.join(SAVE_DIR, site_dir)
    session = build_session(referer=PAGE_URL)

    try:
        html = fetch_html(session, PAGE_URL)
    except Exception as e:
        print(f"❌ Не удалось получить страницу: {e}")
        return

    if SAVE_HTML:
        os.makedirs(save_path, exist_ok=True)
        html_path = os.path.join(save_path, "page.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"💾 HTML сохранён в {html_path} (для отладки)")

    soup = BeautifulSoup(html, "html.parser")
    os.makedirs(save_path, exist_ok=True)
    imgs = soup.find_all("img")

    existing_files = [
        f for f in os.listdir(save_path)
        if os.path.isfile(os.path.join(save_path, f))
        and not f.lower().endswith((".html", ".htm", ".txt"))
        and os.path.getsize(os.path.join(save_path, f)) > 0
    ]
    print(f"🔍 Найдено <img> на странице: {len(imgs)}")
    print(f"📁 Уже есть в папке: {len(existing_files)} файлов")
    print(f"📂 Папка: {save_path}")
    if MAX_IMAGES is not None:
        print(f"🎯 Лимит новых скачиваний: {MAX_IMAGES}")

    downloaded, skipped, failed = 0, 0, 0
    last_err = None

    for idx, img in enumerate(imgs):
        if MAX_IMAGES is not None and downloaded >= MAX_IMAGES:
            print(f"\n✋ Достигнут лимит {MAX_IMAGES} новых картинок — останавливаемся.")
            break

        raw = pick_best_url(img)
        if not raw:
            continue

        if raw.startswith("data:"):
            filename = f"embedded_{idx}.png"
            filepath = os.path.join(save_path, filename)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                skipped += 1
                continue
            fname, size = save_base64_image(raw, save_path, idx)
            if fname:
                print(f"✅ [{downloaded+1}/{MAX_IMAGES or '∞'}] {fname}  (base64, {size//1024} КБ)")
                downloaded += 1
            else:
                failed += 1
                print(f"⚠️ Не удалось декодировать base64 (img #{idx})")
            continue

        full_url = urljoin(base_url, raw)
        upgraded = upgrade_url(full_url)
        filename = get_safe_filename(upgraded, idx)
        filepath = os.path.join(save_path, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            skipped += 1
            continue

        candidates = [upgraded]
        if upgraded != full_url:
            candidates.append(full_url)

        success = False
        for try_url in candidates:
            try:
                r = session.get(try_url, timeout=(5, 20), stream=True,
                                headers={"Referer": PAGE_URL})
                r.raise_for_status()
                ctype = r.headers.get("Content-Type", "")
                if not (
                    "image" in ctype
                    or "octet-stream" in ctype
                    or try_url.lower().endswith(".svg")
                ):
                    continue

                size = 0
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(16384):
                        f.write(chunk)
                        size += len(chunk)

                print(f"✅ [{downloaded+1}/{MAX_IMAGES or '∞'}] {filename}  ({size//1024} КБ)")
                downloaded += 1
                success = True
                break
            except Exception as e:
                last_err = e

        if not success:
            failed += 1
            print(f"⚠️ {full_url[:80]}... → {type(last_err).__name__ if last_err else '?'}")

        if DELAY:
            time.sleep(DELAY)

    final_files = [
        f for f in os.listdir(save_path)
        if os.path.isfile(os.path.join(save_path, f))
        and not f.lower().endswith((".html", ".htm", ".txt"))
        and os.path.getsize(os.path.join(save_path, f)) > 0
    ]

    print(f"\n📊 Итог:")
    print(f"   ✅ Новых скачано: {downloaded}")
    print(f"   ⏭️  Пропущено (уже были): {skipped}")
    print(f"   ⚠️  Ошибок: {failed}")
    print(f"   📦 Всего файлов в папке: {len(final_files)}")
    print(f"   📂 {os.path.abspath(save_path)}")

if __name__ == "__main__":
    download_images()
