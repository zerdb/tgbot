import asyncio
import hashlib
import html
import logging
import os
import re
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN_FILE = Path(__file__).resolve().parent.parent / "token.txt"
DB_FILE = Path(__file__).resolve().parent / "sueta05.db"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
dp = Dispatcher()

# Пользователи, которые сейчас находятся в ленте. Ключ — Telegram user_id,
# значение — параметры открытой ленты. Используется для мгновенного обновления
# ленты после публикации нового поста без спама всем подряд.
active_feeds: dict[int, dict] = {}
active_suetas: dict[int, int] = {}
active_sueta_views: dict[int, int] = {}



class PostStates(StatesGroup):
    waiting_content = State()


class SuetaStates(StatesGroup):
    waiting_name = State()
    waiting_text = State()


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, phone TEXT,
            alias TEXT, city TEXT, joined_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, text TEXT,
            media_type TEXT, media_id TEXT, media_caption TEXT,
            city TEXT NOT NULL DEFAULT 'Весь Дагестан', created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS likes (
            post_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            PRIMARY KEY(post_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS suetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, city TEXT NOT NULL,
            creator_id INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sueta_members (
            sueta_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            PRIMARY KEY(sueta_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS sueta_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sueta_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            text TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS alias_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            user_id INTEGER UNIQUE, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS sueta_name_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
            used_count INTEGER NOT NULL DEFAULT 0
        );
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        for name, definition in (("phone", "TEXT"), ("alias", "TEXT"), ("city", "TEXT")):
            if name not in columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        post_columns = {row["name"] for row in conn.execute("PRAGMA table_info(posts)")}
        for name, definition in (
            ("text", "TEXT"), ("media_type", "TEXT"), ("media_id", "TEXT"),
            ("media_caption", "TEXT"), ("city", "TEXT NOT NULL DEFAULT 'Весь Дагестан'")
        ):
            if name not in post_columns:
                conn.execute(f"ALTER TABLE posts ADD COLUMN {name} {definition}")

        cities = ("Весь Дагестан", "Махачкала", "Буйнакск", "Дербент", "Каспийск", "Хасавюрт", "Избербаш", "Кизляр")
        alias_bases = (
            "Барс", "Чебурек", "Лезгинский Самовар", "Горный Орёл", "Суетолог", "Каспийский Кот",
            "Дербентский Ветер", "Буйнакский Шаман", "Махачкалинский Фанат", "Хинкал", "Аулский Ниндзя",
            "Горный Кабан", "Каспийский Шторм", "Горный Енот", "Хинкальный Босс", "Дербентский Лис",
            "Махачкалинский Кекс", "Буйнакский Беркут", "Каспийский Пацан", "Аульный Философ", "Суетной Барон",
            "Хан Хинкала", "Горный Пельмень", "Чайный Авторитет", "Кот с Перевала", "Легенда Аула",
            "Шашлычный Магистр", "Самоварный Рейдер", "Орёл с Балкона", "Хинкальный Ниндзя", "Каспийский Пират",
            "Буйнакский Турист", "Дербентский Гром", "Махачкалинский Сокол", "Горный Краб", "Аульный Командир",
            "Суетный Медведь", "Чебуречный Философ", "Каспийский Шериф", "Дагестанский Дрифт", "Горный Бродяга",
            "Хинкальный Бандит", "Самоварный Капитан", "Кот из Дербента", "Суетолог Максимум", "Горный Дядька",
            "Аульный Рок-н-ролл", "Каспийский Дракон", "Буйнакский Ракетчик", "Дербентский Романтик",
            "Махачкалинский Тигр", "Хинкалозавр", "Горный Сапёр", "Суетной Профессор", "Каспийский Краб",
            "Чайный Терминатор", "Ауловый Штурман", "Дербентский Кот", "Махачкалинский Метеор", "Горный Гопник",
            "Хинкальный Инженер", "Каспийский Воробей", "Суетной Пилот", "Буйнакский Медведь", "Самоварный Шаман",
            "Дагестанский Пингвин", "Горный Таксист", "Чебуречный Рейнджер", "Каспийский Вихрь", "Дербентский Хулиган",
            "Махачкалинский Бум", "Аульный Барс", "Хинкальный Космонавт", "Суетной Депутат", "Горный Кот",
            "Каспийский Громила", "Буйнакский Фокусник", "Самоварный Босс", "Дербентский Штурман", "Махачкалинский Кабан",
            "Аульный Кот", "Хинкальный Самурай", "Суетной Десантник", "Горный Ветер", "Каспийский Бегемот",
            "Буйнакский Орёл", "Чайный Барон", "Дербентский Пельмень", "Махачкалинский Ниндзя", "Аульный Космонавт",
            "Хинкальный Барс", "Суетной Капитан", "Горный Фанат", "Каспийский Самовар", "Дербентский Сокол",
            "Каспийский Хулиган", "Горный Шахматист", "Махачкалинский Барс", "Аульный Босс", "Чебуречный Барон",
            "Дербентский Пацан", "Суетной Орёл", "Горный Рыцарь", "Каспийский Фанат", "Хинкальный Профессор",
            "Махачкалинский Гром"
        )
        sueta_templates = ("После шести", "Кто куда?", "Город шумит", "На связи", "Пятничная суета", "Без паники", "Есть разговор")
        now = datetime.now().isoformat(timespec="seconds")
        conn.executemany("INSERT OR IGNORE INTO cities(name, sort_order) VALUES (?, ?)", [(v, i) for i, v in enumerate(cities)])
        conn.executemany("INSERT OR IGNORE INTO alias_bases(name, sort_order) VALUES (?, ?)", [(v, i) for i, v in enumerate(alias_bases)])
        conn.executemany("INSERT OR IGNORE INTO sueta_name_templates(name, sort_order) VALUES (?, ?)", [(v, i) for i, v in enumerate(sueta_templates)])
        for row in conn.execute("SELECT user_id, alias FROM users WHERE alias IS NOT NULL AND alias != ''"):
            conn.execute("INSERT OR IGNORE INTO aliases(name, user_id, created_at) VALUES (?, ?, ?)", (row["alias"], row["user_id"], now))


def get_cities(conn=None) -> list[str]:
    if conn is not None:
        return [r["name"] for r in conn.execute(
            "SELECT name FROM cities WHERE active=1 ORDER BY sort_order, id"
        ).fetchall()]
    with db() as local_conn:
        return [r["name"] for r in local_conn.execute(
            "SELECT name FROM cities WHERE active=1 ORDER BY sort_order, id"
        ).fetchall()]


def allocate_alias(conn, user_id: int, username: str | None, phone: str | None) -> str:
    existing = conn.execute("SELECT name FROM aliases WHERE user_id=?", (user_id,)).fetchone()
    if existing:
        return existing["name"]
    bases = conn.execute("SELECT name FROM alias_bases WHERE active=1 ORDER BY sort_order, id").fetchall()
    if not bases:
        raise RuntimeError("В базе нет доступных основ для анонимных имён.")
    seed = f"{phone or ''}|{username or ''}|{user_id}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    start = int(digest[:8], 16) % len(bases)
    for salt in range(len(bases) + 100):
        base = bases[(start + salt) % len(bases)]["name"]
        suffix = hashlib.sha256(f"{digest}|{salt}".encode("utf-8")).hexdigest()[:6].upper()
        candidate = f"{base} {suffix}"
        try:
            conn.execute("INSERT INTO aliases(name, user_id, created_at) VALUES (?, ?, ?)",
                         (candidate, user_id, datetime.now().isoformat(timespec="seconds")))
            return candidate
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Не удалось выдать уникальное анонимное имя.")


def register_user(user, phone: str | None = None) -> None:
    if not user:
        return
    with db() as conn:
        old = conn.execute("SELECT phone, alias, city FROM users WHERE user_id=?", (user.id,)).fetchone()
        stored_phone = phone or (old["phone"] if old else None)
        if old and old["alias"]:
            alias = old["alias"]
            conn.execute("INSERT OR IGNORE INTO aliases(name, user_id, created_at) VALUES (?, ?, ?)",
                         (alias, user.id, datetime.now().isoformat(timespec="seconds")))
        else:
            alias = allocate_alias(conn, user.id, user.username, stored_phone)
        # Город больше не участвует в пользовательской логике.
        # Оставляем legacy-значение в БД только для совместимости со старой схемой.
        city = old["city"] if old and old["city"] else "Весь Дагестан"
        conn.execute(
            """INSERT INTO users(user_id, username, first_name, phone, alias, city, joined_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               username=excluded.username, first_name=excluded.first_name,
               phone=COALESCE(excluded.phone, users.phone), alias=excluded.alias, city=excluded.city""",
            (user.id, user.username, user.first_name, stored_phone, alias, city, datetime.now().isoformat(timespec="seconds")),
        )


def display_name(row) -> str:
    return html.escape(row["alias"] or "Аноним 05")


def time_ago(iso: str) -> str:
    try:
        seconds = max(0, int((datetime.now() - datetime.fromisoformat(iso)).total_seconds()))
    except ValueError:
        return ""
    if seconds < 60:
        return "только что"
    if seconds < 3600:
        return f"{seconds // 60} мин назад"
    if seconds < 86400:
        return f"{seconds // 3600} ч назад"
    return f"{seconds // 86400} дн назад"


def feed(limit=10, offset=0, city=None, hot=False):
    order = "((SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) * 3 - (julianday('now') - julianday(p.created_at)) * 2) DESC, p.id DESC" if hot else "p.id DESC"
    where = "" if not city or city == "Весь Дагестан" else "WHERE p.city=?"
    params = [] if not city or city == "Весь Дагестан" else [city]
    with db() as conn:
        return conn.execute(f"""
            SELECT p.*, u.alias,
                   (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes
            FROM posts p JOIN users u ON u.user_id=p.user_id
            {where}
            ORDER BY {order} LIMIT ? OFFSET ?
        """, (*params, limit, offset)).fetchall()


def post_text(row) -> str:
    body = html.escape(row["text"] or row["media_caption"] or "")
    if row["media_type"] == "photo":
        body = "📷 " + body
    elif row["media_type"] == "video":
        body = "🎥 " + body
    elif row["media_type"] == "voice":
        body = "🎙 Голосовое сообщение"
    elif row["media_type"] == "location":
        body = "📍 Геолокация"
    elif row["media_type"] == "link":
        body = "🔗 " + body

    return (
        f"👤 <b>{display_name(row)}</b>\n"
        f"🕒 <i>{time_ago(row['created_at'])}</i>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{body}\n\n"
        f"❤️ {row['likes']}"
    )


def main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔥 Горячее", callback_data="hot:0"),
        InlineKeyboardButton(text="➕ Запостить", callback_data="post"),
    )
    b.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
    )
    return b.as_markup()


def load_suetas(limit=15):
    with db() as conn:
        return conn.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM sueta_members sm WHERE sm.sueta_id=s.id) members,
                      (SELECT COUNT(*) FROM sueta_messages sx WHERE sx.sueta_id=s.id) messages_count
               FROM suetas s
               ORDER BY s.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def suetas_screen_text(rows):
    if rows:
        return (
            "💬 <b>Суеты</b>\n\n"
            "Выбирай разговор и заходи."
        )
    return (
        "💬 <b>Суеты</b>\n\n"
        "Пока никто не создал ни одной суеты.\n"
        "Будь первым."
    )


def suetas_screen_keyboard(rows):
    if rows:
        return sueta_keyboard(rows)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Создать суету", callback_data="new_sueta"))
    return b.as_markup()


async def push_new_post_to_active_feeds(bot: Bot, author_id: int):
    """Перерисовывает открытые ленты после публикации нового поста."""
    with db() as conn:
        row = conn.execute(
            """SELECT p.*, u.alias,
                      (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes
               FROM posts p JOIN users u ON u.user_id=p.user_id
               WHERE p.id=(SELECT MAX(id) FROM posts WHERE user_id=? )""",
            (author_id,),
        ).fetchone()
    if not row:
        return

    recipients = list(active_feeds.items())
    for user_id, view in recipients:
        city = view.get("city")
        if city and city != "Весь Дагестан" and row["city"] != city:
            continue
        try:
            await show_feed(
                bot,
                user_id,
                offset=view.get("offset", 0),
                city=city,
                hot=view.get("hot", False),
            )
        except Exception:
            logger.warning("Не удалось обновить ленту user_id=%s", user_id, exc_info=True)
            active_feeds.pop(user_id, None)

def post_keyboard(post_id: int, liked=False):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❤️" if not liked else "💔", callback_data=f"like:{post_id}"))
    return b.as_markup()


def nav_keyboard(kind: str, offset: int, has_next: bool):
    b = InlineKeyboardBuilder()
    buttons = []
    prefix = "hot" if kind == "hot" else "feed"
    if offset > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Новее", callback_data=f"{prefix}:{max(0, offset-10)}"))
    if has_next:
        buttons.append(InlineKeyboardButton(text="Старее ➡️", callback_data=f"{prefix}:{offset+10}"))
    if buttons:
        b.row(*buttons)
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    return b.as_markup()


def sueta_keyboard(rows):
    b = InlineKeyboardBuilder()
    for row in rows:
        b.button(
            text=f"💬 {row['name']} · 👥 {row['members']}",
            callback_data=f"sueta:{row['id']}",
        )
    b.adjust(1)
    b.row(InlineKeyboardButton(text="➕ Создать свою суету", callback_data="new_sueta"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    return b.as_markup()


def get_home_text() -> str:
    return (
        "🌀 <b>SUETA 05</b>\n\n"
        "Дагестанская лента внутри Telegram.\n"
        "Пиши, что происходит. Смотри, что происходит.\n"
        "Здесь все — под прикольными анонимными именами.\n\n"
        "🔥 Дагестанская суета · 🔥 Горячее\n"
        "💬 Суеты пользователей · ➕ Посты · 👤 Профиль"
    )


def compact_post_text(row) -> str:
    body = html.escape(row["text"] or row["media_caption"] or "")
    if not body:
        body = {
            "voice": "🎙 Голосовое сообщение",
            "location": "📍 Геолокация",
        }.get(row["media_type"], "")
    return (
        f"👤 <b>{display_name(row)}</b> · <i>{time_ago(row['created_at'])}</i>\n"
        f"{body}\n"
        f"❤️ {row['likes']}"
    )


async def show_feed(target, user_id: int, offset=0, city=None, hot=False):
    """Показывает ленту как компактный поток сообщений, сохраняя порядок."""
    previous = active_feeds.get(user_id, {})
    previous_ids = previous.get("message_ids", [])

    bot = target.bot if isinstance(target, (types.CallbackQuery, Message)) else target
    chat_id = user_id

    for message_id in previous_ids:
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    page_size = 6
    rows = feed(limit=page_size, offset=offset, city=city, hot=hot)
    sent_ids = []

    if not rows:
        msg = await bot.send_message(
            chat_id,
            "🔥 <b>Дагестан</b>\n\nПока пусто. Устрой первую суету.",
            reply_markup=main_keyboard(),
        )
        sent_ids.append(msg.message_id)
        active_feeds[user_id] = {
            "city": city, "hot": hot, "offset": offset, "message_ids": sent_ids,
        }
        return

    # Не сортируем медиа отдельно: иначе фото/видео уезжают от сообщения,
    # к которому они относятся. Собираем только соседние текстовые сообщения.
    text_chunk = []

    async def flush_text_chunk():
        nonlocal text_chunk
        if not text_chunk:
            return

        keyboard = InlineKeyboardBuilder()
        for row in text_chunk:
            with db() as conn:
                liked = conn.execute(
                    "SELECT 1 FROM likes WHERE post_id=? AND user_id=?",
                    (row["id"], user_id),
                ).fetchone()
            keyboard.row(
                InlineKeyboardButton(
                    text=f"{'💔' if liked else '❤️'} {row['likes']}",
                    callback_data=f"like:{row['id']}",
                )
            )

        msg = await bot.send_message(
            chat_id,
            "\n\n".join(compact_post_text(row) for row in text_chunk),
            reply_markup=keyboard.as_markup(),
        )
        sent_ids.append(msg.message_id)
        text_chunk = []

    for row in rows:
        media_type = row["media_type"]

        if media_type not in ("photo", "video", "voice", "location"):
            text_chunk.append(row)
            continue

        await flush_text_chunk()

        with db() as conn:
            liked = conn.execute(
                "SELECT 1 FROM likes WHERE post_id=? AND user_id=?",
                (row["id"], user_id),
            ).fetchone()

        markup = post_keyboard(row["id"], bool(liked))

        if media_type == "photo":
            msg = await bot.send_photo(
                chat_id, row["media_id"], caption=compact_post_text(row),
                reply_markup=markup,
            )
            sent_ids.append(msg.message_id)

        elif media_type == "video":
            msg = await bot.send_video(
                chat_id, row["media_id"], caption=compact_post_text(row),
                reply_markup=markup,
            )
            sent_ids.append(msg.message_id)

        elif media_type == "voice":
            msg = await bot.send_voice(
                chat_id, row["media_id"], caption=compact_post_text(row),
                reply_markup=markup,
            )
            sent_ids.append(msg.message_id)

        elif media_type == "location":
            msg = await bot.send_location(
                chat_id,
                float(row["media_id"].split(",")[0]),
                float(row["media_id"].split(",")[1]),
                reply_markup=markup,
            )
            sent_ids.append(msg.message_id)

    await flush_text_chunk()

    # Навигация отдельным коротким сообщением только внизу страницы.
    nav = await bot.send_message(
        chat_id,
        "🔥 Дагестан" if not hot else "🔥 Горячее",
        reply_markup=nav_keyboard(
            "hot" if hot else "feed",
            offset,
            len(rows) == page_size,
        ),
    )
    sent_ids.append(nav.message_id)

    active_feeds[user_id] = {
        "city": city,
        "hot": hot,
        "offset": offset,
        "message_ids": sent_ids,
    }


async def show_suetas_screen(target):
    rows = load_suetas()
    text = suetas_screen_text(rows)
    markup = suetas_screen_keyboard(rows)

    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    try:
        register_user(message.from_user)
        await state.clear()
        await show_suetas_screen(message)
    except Exception:
        logger.exception("Ошибка обработки /start для user_id=%s", message.from_user.id)
        await message.answer("⚠️ Не удалось открыть SUETA 05. Ошибка уже записана в лог.")


@dp.message(Command("menu"))
async def menu(message: Message, state: FSMContext):
    await state.clear()
    register_user(message.from_user)
    await show_suetas_screen(message)


@dp.callback_query(F.data == "home")
async def home(callback: types.CallbackQuery, state: FSMContext):
    active_feeds.pop(callback.from_user.id, None)
    active_suetas.pop(callback.from_user.id, None)
    active_sueta_views.pop(callback.from_user.id, None)
    await callback.answer()
    await state.clear()
    await show_suetas_screen(callback)


@dp.callback_query(F.data == "feed:0")
async def open_feed(callback: types.CallbackQuery):
    await callback.answer()
    await show_feed(callback, callback.from_user.id)


@dp.callback_query(F.data.startswith("feed:"))
async def feed_page(callback: types.CallbackQuery):
    await callback.answer()
    await show_feed(callback, callback.from_user.id, int(callback.data.split(":")[1]))


@dp.callback_query(F.data.startswith("hot:"))
async def hot_page(callback: types.CallbackQuery):
    await callback.answer()
    await show_feed(callback, callback.from_user.id, int(callback.data.split(":")[1]), hot=True)



@dp.callback_query(F.data == "post")
async def create_post(callback: types.CallbackQuery, state: FSMContext):
    active_feeds.pop(callback.from_user.id, None)
    await callback.answer()
    await state.set_state(PostStates.waiting_content)
    await callback.message.answer(
        "➕ <b>Новая суета</b>\n\n"
        "Это общий Дагестанский поток.\n"
        "Принимаю: текст, 📷 фото, 🎥 видео, 🎙 голосовое, 📍 геолокацию и 🔗 ссылки.\n"
        "Можно добавить подпись к медиа.\n\n"
        "Просто отправь сообщение — оно сразу появится в суете."
    )


@dp.message(PostStates.waiting_content)
async def save_post(message: Message, state: FSMContext):
    register_user(message.from_user)
    media_type = None
    media_id = None
    text = None
    caption = (message.caption or "").strip()

    if message.photo:
        media_type, media_id = "photo", message.photo[-1].file_id
        text = caption
    elif message.video:
        media_type, media_id = "video", message.video.file_id
        text = caption
    elif message.voice:
        media_type, media_id = "voice", message.voice.file_id
        text = caption
    elif message.location:
        media_type, media_id = "location", f"{message.location.latitude},{message.location.longitude}"
        text = caption or "Геолокация"
    elif message.text:
        text = message.text.strip()
        if re.match(r"^https?://", text):
            media_type = "link"
    else:
        await message.answer("Такой формат пока не принимаю.")
        return

    if not text and media_type not in ("voice", "location"):
        await message.answer("Добавь немного суеты — текст или подпись.")
        return
    max_length = 900 if media_type in ("photo", "video", "voice") else 1000
    if len(text or "") > max_length:
        await message.answer(
            f"Слишком много суеты 😄 Максимум {max_length} символов для этого формата."
        )
        return

    with db() as conn:
        conn.execute(
            """INSERT INTO posts(user_id, text, media_type, media_id, media_caption, city, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                message.from_user.id,
                text or "",
                media_type,
                media_id,
                text or "",
                "Весь Дагестан",
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    await state.clear()
    await message.answer("🔥 <b>Суета опубликована в Дагестане.</b>", reply_markup=main_keyboard())
    await push_new_post_to_active_feeds(message.bot, message.from_user.id)


@dp.callback_query(F.data.startswith("like:"))
async def like(callback: types.CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    with db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM likes WHERE post_id=? AND user_id=?",
            (post_id, callback.from_user.id),
        ).fetchone()
        if exists:
            conn.execute(
                "DELETE FROM likes WHERE post_id=? AND user_id=?",
                (post_id, callback.from_user.id),
            )
            await callback.answer("Лайк убран")
        else:
            conn.execute(
                "INSERT OR IGNORE INTO likes(post_id, user_id) VALUES (?, ?)",
                (post_id, callback.from_user.id),
            )
            await callback.answer("❤️ Лайк!")

    # Перерисовываем текущую страницу, чтобы счётчик и клавиатура
    # оставались корректными и для обычного текста, и для медиа.
    view = active_feeds.get(callback.from_user.id)
    if view:
        await show_feed(
            callback,
            callback.from_user.id,
            offset=view.get("offset", 0),
            city=view.get("city"),
            hot=view.get("hot", False),
        )


@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    register_user(callback.from_user)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (callback.from_user.id,)).fetchone()
        posts = conn.execute("SELECT COUNT(*) c FROM posts WHERE user_id=?", (callback.from_user.id,)).fetchone()["c"]
        likes = conn.execute("SELECT COUNT(*) c FROM likes l JOIN posts p ON p.id=l.post_id WHERE p.user_id=?", (callback.from_user.id,)).fetchone()["c"]
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>Профиль</b>\n\n"
        f"🌀 Имя: <b>{display_name(user)}</b>\n"

        f"🔥 Постов: <b>{posts}</b>\n"
        f"❤️ Лайков на твоих постах: <b>{likes}</b>",
        reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню", callback_data="home").as_markup(),
    )


@dp.callback_query(F.data == "suitas")
async def suitas(callback: types.CallbackQuery):
    await callback.answer()
    await show_suetas_screen(callback)


@dp.callback_query(F.data == "new_sueta")
async def new_sueta(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SuetaStates.waiting_name)
    await callback.message.edit_text(
        "➕ <b>Создать свою суету</b>\n\n"
        "Придумай название — до 80 символов.\n\n"
        "Например:\n"
        "«Кто сегодня на море?»\n"
        "«Вечерняя тусовка»\n"
        "«Что происходит?»"
    )


@dp.message(SuetaStates.waiting_name)
async def save_sueta_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Напиши название суеты текстом.")
        return
    name = message.text.strip()
    if not name or len(name) > 80:
        await message.answer("Название должно быть от 1 до 80 символов.")
        return

    register_user(message.from_user)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO suetas(name, city, creator_id, created_at) VALUES (?, ?, ?, ?)",
            (name, "Дагестан", message.from_user.id, datetime.now().isoformat(timespec="seconds")),
        )
        sueta_id = cur.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO sueta_members(sueta_id, user_id) VALUES (?, ?)",
            (sueta_id, message.from_user.id),
        )

    await state.clear()
    await message.answer(
        f"💬 <b>{html.escape(name)}</b>\n\n"
        "👥 1 участник\n"
        "🔥 0 сообщений\n\n"
        "Суета создана. Можно звать людей.",
        reply_markup=InlineKeyboardBuilder().button(
            text="💬 Открыть суету", callback_data=f"sueta:{sueta_id}"
        ).as_markup(),
    )


def sueta_view(sueta_id: int):
    with db() as conn:
        sueta = conn.execute("SELECT * FROM suetas WHERE id=?", (sueta_id,)).fetchone()
        if not sueta:
            return None, None
        members = conn.execute("SELECT COUNT(*) c FROM sueta_members WHERE sueta_id=?", (sueta_id,)).fetchone()["c"]
        messages_count = conn.execute("SELECT COUNT(*) c FROM sueta_messages WHERE sueta_id=?", (sueta_id,)).fetchone()["c"]
        messages = conn.execute("""SELECT m.*, u.alias FROM sueta_messages m JOIN users u ON u.user_id=m.user_id WHERE m.sueta_id=? ORDER BY m.id DESC LIMIT 30""", (sueta_id,)).fetchall()

    lines = [f"📌 <b>{html.escape(sueta['name'])}</b>", f"👥 {members} · 💬 {messages_count}", ""]
    if messages:
        for row in reversed(messages):
            lines.append(f"<b>{display_name(row)}</b> · <i>{time_ago(row['created_at'])}</i>\n{html.escape(row['text'])}")
    else:
        lines.append("Пока тихо. Напиши первое сообщение прямо из строки Telegram.")

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🚪 Выйти из суеты", callback_data=f"leave_sueta:{sueta_id}"))
    b.row(InlineKeyboardButton(text="💬 Сменить суету", callback_data="suitas"))
    return "\n\n".join(lines), b.as_markup()


@dp.callback_query(F.data.startswith("sueta:"))
async def open_sueta(callback: types.CallbackQuery, state: FSMContext):
    sueta_id = int(callback.data.split(":")[1])
    register_user(callback.from_user)

    with db() as conn:
        sueta = conn.execute("SELECT * FROM suetas WHERE id=?", (sueta_id,)).fetchone()
        if not sueta:
            await callback.answer("Суета не найдена.", show_alert=True)
            return
        conn.execute("INSERT OR IGNORE INTO sueta_members(sueta_id, user_id) VALUES (?, ?)", (sueta_id, callback.from_user.id))

    active_suetas[callback.from_user.id] = sueta_id
    active_feeds.pop(callback.from_user.id, None)
    await state.clear()
    await callback.answer("Суета закреплена 🔥")
    view_text, view_markup = sueta_view(sueta_id)
    await callback.message.edit_text(view_text, reply_markup=view_markup)
    active_sueta_views[callback.from_user.id] = callback.message.message_id

@dp.callback_query(F.data.startswith("leave_sueta:"))
async def leave_sueta(callback: types.CallbackQuery, state: FSMContext):
    sueta_id = int(callback.data.split(":")[1])
    with db() as conn:
        conn.execute(
            "DELETE FROM sueta_members WHERE sueta_id=? AND user_id=?",
            (sueta_id, callback.from_user.id),
        )
    active_suetas.pop(callback.from_user.id, None)
    active_sueta_views.pop(callback.from_user.id, None)
    await state.clear()
    await callback.answer("Ты вышел из суеты.")
    await show_suetas_screen(callback)


@dp.message()
async def active_sueta_message(message: Message, state: FSMContext):
    """Любое обычное сообщение идёт в закреплённую суету."""
    if message.text and message.text.startswith("/"):
        return

    sueta_id = active_suetas.get(message.from_user.id)
    if not sueta_id:
        return

    register_user(message.from_user)

    if not message.text:
        await message.answer("В суете пока принимаю сообщения только текстом.")
        return

    text = message.text.strip()
    if not text or len(text) > 500:
        await message.answer("Сообщение: от 1 до 500 символов.")
        return

    with db() as conn:
        member = conn.execute(
            "SELECT 1 FROM sueta_members WHERE sueta_id=? AND user_id=?",
            (sueta_id, message.from_user.id),
        ).fetchone()
        sueta = conn.execute(
            "SELECT name FROM suetas WHERE id=?", (sueta_id,)
        ).fetchone()

        if not member or not sueta:
            active_suetas.pop(message.from_user.id, None)
            await message.answer("Суета больше недоступна. Выбери другую.")
            return

        conn.execute(
            "INSERT INTO sueta_messages(sueta_id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
            (
                sueta_id,
                message.from_user.id,
                text,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

    # Убираем исходное сообщение пользователя из личного чата с ботом,
    # чтобы Telegram не оставлял локальный "след". Само сообщение уже
    # сохранено в общей суете и появится в едином окне чата.
    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить исходное сообщение user_id=%s", message.from_user.id, exc_info=True)

    # Не отправляем отдельное подтверждение: обновляем единое сообщение общего чата.
    view_message_id = active_sueta_views.get(message.from_user.id)
    if view_message_id:
        view_text, view_markup = sueta_view(sueta_id)
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=view_message_id,
                text=view_text,
                reply_markup=view_markup,
            )
        except Exception:
            logger.warning("Не удалось обновить общий чат суеты user_id=%s sueta_id=%s", message.from_user.id, sueta_id, exc_info=True)


@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📍 <b>SUETA 05</b>\n\n"
        "Локальная соцсеть Дагестана внутри Telegram.\n\n"
        "В ленте — общий поток по всему Дагестану.\n"
        "Отдельные разговоры пользователи создают в своих суетах.\n"
        "Имена — анонимные и генерируются автоматически.\n"
        "Телефон и Telegram username используются только внутри базы и не показываются пользователям.",
        reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню", callback_data="home").as_markup(),
    )


def detect_proxy() -> str | None:
    explicit = os.getenv("BOT_PROXY", "").strip()
    if explicit:
        return explicit
    proxies = urllib.request.getproxies()
    return proxies.get("https") or proxies.get("http")


def load_token() -> str:
    token = os.getenv("BOT_TOKEN", "").strip()
    if token:
        return token
    for path in (TOKEN_FILE, Path.cwd() / "token.txt", Path(__file__).resolve().parent / "token.txt"):
        if path.is_file():
            token = path.read_text(encoding="utf-8-sig").strip().strip('"').strip("'").strip()
            if token:
                return token
    raise RuntimeError("Не найден токен. Используй BOT_TOKEN или token.txt.")


async def main():
    from aiogram.client.session.aiohttp import AiohttpSession
    init_db()
    proxy = detect_proxy()
    session = AiohttpSession(proxy=proxy) if proxy else AiohttpSession()
    bot = Bot(
        token=load_token(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.info("SUETA 05 запускается...")
    try:
        # На всякий случай сбрасываем webhook: polling не получает апдейты,
        # если бот ранее был переведен в webhook-режим.
        webhook = await bot.get_webhook_info()
        if webhook.url:
            logger.warning("Найден webhook %s — удаляем перед polling.", webhook.url)
            await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Telegram webhook очищен, запускаем polling.")
        while True:
            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                break
            except Exception as exc:
                logger.exception("Ошибка Telegram API. Повтор через 15 секунд: %s", exc)
                await asyncio.sleep(15)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
