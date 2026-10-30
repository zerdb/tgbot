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


class PostStates(StatesGroup):
    waiting_content = State()
    waiting_city = State()


class SuetaStates(StatesGroup):
    waiting_name = State()
    waiting_city = State()
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
        cities = get_cities(conn)
        if not cities:
            raise RuntimeError("В базе нет активных городов.")
        city = old["city"] if old and old["city"] else cities[0]
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
        f"🔥 <b>{display_name(row)}</b> · <i>{time_ago(row['created_at'])}</i>\n"
        f"📍 {html.escape(row['city'])}\n\n{body}\n\n"
        f"❤️ {row['likes']}"
    )


def main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔥 Лента", callback_data="feed:0"),
        InlineKeyboardButton(text="🔥 Горячее", callback_data="hot:0"),
    )
    b.row(
        InlineKeyboardButton(text="➕ Запостить", callback_data="post"),
        InlineKeyboardButton(text="📍 Мой город", callback_data="cities"),
    )
    b.row(
        InlineKeyboardButton(text="💬 Мини-суеты", callback_data="suitas"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
    )
    return b.as_markup()


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


def city_keyboard():
    b = InlineKeyboardBuilder()
    for city in get_cities():
        b.button(text=f"📍 {city}", callback_data=f"city:{city}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    return b.as_markup()


def sueta_keyboard(rows):
    b = InlineKeyboardBuilder()
    for row in rows:
        b.button(
            text=f"💬 {row['name']} · {row['city']} · 👥 {row['members']}",
            callback_data=f"sueta:{row['id']}",
        )
    b.adjust(1)
    b.row(InlineKeyboardButton(text="➕ Создать суету", callback_data="new_sueta"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    return b.as_markup()


def sueta_city_keyboard():
    b = InlineKeyboardBuilder()
    for city in get_cities():
        b.button(text=f"📍 {city}", callback_data=f"suetacity:{city}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    return b.as_markup()


def get_home_text() -> str:
    return (
        "🌀 <b>SUETA 05</b>\n\n"
        "Дагестанская лента внутри Telegram.\n"
        "Пиши, что происходит. Смотри, что происходит.\n"
        "Здесь все — под прикольными анонимными именами.\n\n"
        "🔥 Лента · 🔥 Горячее · 📍 Города\n"
        "💬 Мини-суеты · ➕ Посты · 👤 Профиль"
    )


async def show_feed(target, user_id: int, offset=0, city=None, hot=False):
    rows = feed(offset=offset, city=city, hot=hot)
    title = "🔥 <b>Горячее</b>" if hot else "🔥 <b>Лента</b>"
    if city and city != "Весь Дагестан":
        title += f" · 📍 {html.escape(city)}"
    if not rows:
        text = f"{title}\n\nПока пусто. Устрой первую суету."
        markup = main_keyboard()
        if isinstance(target, types.CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup)
        else:
            await target.answer(text, reply_markup=markup)
        return
    for index, row in enumerate(rows):
        with db() as conn:
            liked = conn.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?", (row["id"], user_id)).fetchone()
        markup = post_keyboard(row["id"], bool(liked))
        if row["media_type"] == "photo":
            if isinstance(target, types.CallbackQuery) and index == 0:
                await target.message.delete()
            await target.bot.send_photo(target.from_user.id, row["media_id"], caption=post_text(row), reply_markup=markup)
        elif row["media_type"] == "video":
            if isinstance(target, types.CallbackQuery) and index == 0:
                await target.message.delete()
            await target.bot.send_video(target.from_user.id, row["media_id"], caption=post_text(row), reply_markup=markup)
        elif row["media_type"] == "voice":
            if isinstance(target, types.CallbackQuery) and index == 0:
                await target.message.delete()
            await target.bot.send_voice(target.from_user.id, row["media_id"], caption=post_text(row), reply_markup=markup)
        elif row["media_type"] == "location":
            if isinstance(target, types.CallbackQuery) and index == 0:
                await target.message.delete()
            await target.bot.send_location(target.from_user.id, float(row["media_id"].split(",")[0]), float(row["media_id"].split(",")[1]))
            await target.bot.send_message(target.from_user.id, post_text(row), reply_markup=markup)
        else:
            if index == 0 and isinstance(target, types.CallbackQuery):
                await target.message.edit_text(post_text(row), reply_markup=markup)
            elif isinstance(target, types.CallbackQuery):
                await target.message.answer(post_text(row), reply_markup=markup)
            else:
                await target.answer(post_text(row), reply_markup=markup)
    if isinstance(target, types.CallbackQuery):
        await target.message.answer(title, reply_markup=nav_keyboard("hot" if hot else "feed", offset, len(rows) == 10))
    else:
        await target.answer(title, reply_markup=nav_keyboard("hot" if hot else "feed", offset, len(rows) == 10))


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    try:
        register_user(message.from_user)
        await state.clear()
        await message.answer(get_home_text(), reply_markup=main_keyboard())
    except Exception:
        logger.exception("Ошибка обработки /start для user_id=%s", message.from_user.id)
        await message.answer("⚠️ Не удалось открыть SUETA 05. Ошибка уже записана в лог.")


@dp.message(Command("menu"))
async def menu(message: Message, state: FSMContext):
    await state.clear()
    register_user(message.from_user)
    await message.answer(get_home_text(), reply_markup=main_keyboard())


@dp.callback_query(F.data == "home")
async def home(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(get_home_text(), reply_markup=main_keyboard())


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


@dp.callback_query(F.data == "cities")
async def cities(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("📍 <b>Суета рядом</b>\n\nВыбери город:", reply_markup=city_keyboard())


@dp.callback_query(F.data.startswith("city:"))
async def choose_city(callback: types.CallbackQuery):
    city = callback.data.split(":", 1)[1]
    register_user(callback.from_user)
    with db() as conn:
        conn.execute("UPDATE users SET city=? WHERE user_id=?", (city, callback.from_user.id))
    await callback.answer(f"Город: {city}")
    await show_feed(callback, callback.from_user.id, city=city)


@dp.callback_query(F.data == "post")
async def create_post(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PostStates.waiting_content)
    await callback.message.answer(
        "➕ <b>Новая суета</b>\n\n"
        "Принимаю: текст, 📷 фото, 🎥 видео, 🎙 голосовое, 📍 геолокацию и 🔗 ссылки.\n"
        "Можно добавить подпись к медиа.\n"
        "После сообщения выберем город."
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
    if len(text or "") > 1000:
        await message.answer("Слишком много суеты 😄 Максимум 1000 символов.")
        return
    await state.update_data(media_type=media_type, media_id=media_id, text=text or "", city=get_cities()[0])
    await state.set_state(PostStates.waiting_city)
    await message.answer("📍 <b>Где эта суета?</b>\n\nМожно выбрать город или весь Дагестан:", reply_markup=city_keyboard())


@dp.callback_query(PostStates.waiting_city, F.data.startswith("city:"))
async def publish_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split(":", 1)[1]
    data = await state.get_data()
    register_user(callback.from_user)
    with db() as conn:
        conn.execute(
            """INSERT INTO posts(user_id, text, media_type, media_id, media_caption, city, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (callback.from_user.id, data.get("text", ""), data.get("media_type"), data.get("media_id"),
             data.get("text", ""), city, datetime.now().isoformat(timespec="seconds")),
        )
    await state.clear()
    await callback.answer("🔥 Опубликовано!")
    await callback.message.edit_text("🔥 <b>Суета опубликована.</b>", reply_markup=main_keyboard())


@dp.callback_query(F.data.startswith("like:"))
async def like(callback: types.CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    with db() as conn:
        exists = conn.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?", (post_id, callback.from_user.id)).fetchone()
        if exists:
            conn.execute("DELETE FROM likes WHERE post_id=? AND user_id=?", (post_id, callback.from_user.id))
            await callback.answer("Лайк убран")
        else:
            conn.execute("INSERT OR IGNORE INTO likes(post_id, user_id) VALUES (?, ?)", (post_id, callback.from_user.id))
            await callback.answer("❤️ Лайк!")
        row = conn.execute("""
            SELECT p.*, u.alias, (SELECT COUNT(*) FROM likes WHERE post_id=p.id) likes
            FROM posts p JOIN users u ON u.user_id=p.user_id WHERE p.id=?
        """, (post_id,)).fetchone()
    await callback.message.edit_text(post_text(row), reply_markup=post_keyboard(post_id, not bool(exists)))


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
        f"📍 Город: <b>{html.escape(user['city'])}</b>\n"
        f"🔥 Постов: <b>{posts}</b>\n"
        f"❤️ Лайков на твоих постах: <b>{likes}</b>",
        reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню", callback_data="home").as_markup(),
    )


@dp.callback_query(F.data == "suitas")
async def suitas(callback: types.CallbackQuery):
    with db() as conn:
        rows = conn.execute(
            """SELECT s.*, 
                      (SELECT COUNT(*) FROM sueta_members sm WHERE sm.sueta_id=s.id) members,
                      (SELECT COUNT(*) FROM sueta_messages sx WHERE sx.sueta_id=s.id) messages_count
               FROM suetas s
               ORDER BY s.id DESC LIMIT 15"""
        ).fetchall()
    await callback.answer()
    await callback.message.edit_text(
        "💬 <b>Суеты</b>\n\n"
        "Каждая суета — отдельный разговор со своей темой, городом и участниками.\n"
        "Выбирай готовую или создавай свою.",
        reply_markup=sueta_keyboard(rows),
    )


@dp.callback_query(F.data == "new_sueta")
async def new_sueta(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SuetaStates.waiting_name)
    await callback.message.edit_text(
        "➕ <b>Создать суету</b>\n\n"
        "Придумай название. Например:\n"
        "«КТО СЕГОДНЯ НА БУЙНАКСК?»\n"
        "«Вечерняя Махачкала»\n"
        "«Кто едет на море?»\n\n"
        "Название: до 80 символов."
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
    await state.update_data(sueta_name=name)
    await state.set_state(SuetaStates.waiting_city)
    await message.answer("📍 <b>Где эта суета?</b>\n\nВыбери город или весь Дагестан:", reply_markup=sueta_city_keyboard())


@dp.callback_query(SuetaStates.waiting_city, F.data.startswith("suetacity:"))
async def save_sueta_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split(":", 1)[1]
    data = await state.get_data()
    register_user(callback.from_user)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO suetas(name, city, creator_id, created_at) VALUES (?, ?, ?, ?)",
            (data["sueta_name"], city, callback.from_user.id, datetime.now().isoformat(timespec="seconds")),
        )
        sueta_id = cur.lastrowid
        conn.execute("INSERT OR IGNORE INTO sueta_members(sueta_id, user_id) VALUES (?, ?)", (sueta_id, callback.from_user.id))
    await state.clear()
    await callback.answer("Суета создана!")
    await callback.message.edit_text(
        f"💬 <b>{html.escape(data['sueta_name'])}</b>\n\n"
        f"📍 {html.escape(city)}\n"
        "👥 1 участник\n"
        "🔥 0 сообщений\n\n"
        "Суета создана. Собирай людей вокруг своей темы.",
        reply_markup=InlineKeyboardBuilder().button(text="💬 Войти в суету", callback_data=f"sueta:{sueta_id}").as_markup(),
    )


@dp.callback_query(F.data.startswith("sueta:"))
async def open_sueta(callback: types.CallbackQuery, state: FSMContext):
    sueta_id = int(callback.data.split(":")[1])
    with db() as conn:
        sueta = conn.execute("SELECT * FROM suetas WHERE id=?", (sueta_id,)).fetchone()
        if not sueta:
            await callback.answer("Суета не найдена.", show_alert=True)
            return
        members = conn.execute("SELECT COUNT(*) c FROM sueta_members WHERE sueta_id=?", (sueta_id,)).fetchone()["c"]
        messages_count = conn.execute("SELECT COUNT(*) c FROM sueta_messages WHERE sueta_id=?", (sueta_id,)).fetchone()["c"]
        joined = conn.execute("SELECT 1 FROM sueta_members WHERE sueta_id=? AND user_id=?", (sueta_id, callback.from_user.id)).fetchone()
        messages = conn.execute(
            """SELECT m.*, u.alias FROM sueta_messages m JOIN users u ON u.user_id=m.user_id
               WHERE m.sueta_id=? ORDER BY m.id DESC LIMIT 15""", (sueta_id,)
        ).fetchall()
    await callback.answer()
    lines = [
        f"💬 <b>{html.escape(sueta['name'])}</b>",
        "",
        f"📍 {html.escape(sueta['city'])}",
        f"👥 {members} {'участник' if members == 1 else 'участников'}",
        f"🔥 {messages_count} сообщений",
        "",
    ]
    if joined:
        if messages:
            for row in reversed(messages):
                lines.append(f"<b>{display_name(row)}</b>: {html.escape(row['text'])}")
        else:
            lines.append("Пока тихо. Начни разговор.")
        lines.append("")
        lines.append("Нажми «✍️ Написать», чтобы добавить сообщение.")
    else:
        lines.append("Войди в суету, чтобы участвовать в разговоре.")
    b = InlineKeyboardBuilder()
    if not joined:
        b.row(InlineKeyboardButton(text="💬 Войти в суету", callback_data=f"join_sueta:{sueta_id}"))
    else:
        b.row(InlineKeyboardButton(text="✍️ Написать", callback_data=f"suetawrite:{sueta_id}"))
        b.row(InlineKeyboardButton(text="🚪 Выйти", callback_data=f"leave_sueta:{sueta_id}"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())


@dp.callback_query(F.data.startswith("join_sueta:"))
async def join_sueta(callback: types.CallbackQuery):
    sueta_id = int(callback.data.split(":")[1])
    register_user(callback.from_user)
    with db() as conn:
        sueta = conn.execute("SELECT id FROM suetas WHERE id=?", (sueta_id,)).fetchone()
        if not sueta:
            await callback.answer("Суета не найдена.", show_alert=True)
            return
        conn.execute("INSERT OR IGNORE INTO sueta_members(sueta_id, user_id) VALUES (?, ?)", (sueta_id, callback.from_user.id))
    await callback.answer("Ты в суете 🔥")
    await open_sueta(callback, None)


@dp.callback_query(F.data.startswith("leave_sueta:"))
async def leave_sueta(callback: types.CallbackQuery):
    sueta_id = int(callback.data.split(":")[1])
    with db() as conn:
        conn.execute("DELETE FROM sueta_members WHERE sueta_id=? AND user_id=?", (sueta_id, callback.from_user.id))
    await callback.answer("Ты вышел из суеты.")
    await open_sueta(callback, None)


@dp.callback_query(F.data.startswith("suetawrite:"))
async def sueta_write(callback: types.CallbackQuery, state: FSMContext):
    sueta_id = int(callback.data.split(":")[1])
    await state.update_data(sueta_id=sueta_id)
    await state.set_state(SuetaStates.waiting_text)
    await callback.answer()
    await callback.message.answer("✍️ Напиши сообщение в суету. До 500 символов.")


@dp.message(SuetaStates.waiting_text)
async def save_sueta_message(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("В мини-суетах пока только текст.")
        return
    text = message.text.strip()
    if not text or len(text) > 500:
        await message.answer("Сообщение: от 1 до 500 символов.")
        return
    data = await state.get_data()
    register_user(message.from_user)
    with db() as conn:
        member = conn.execute(
            "SELECT 1 FROM sueta_members WHERE sueta_id=? AND user_id=?",
            (data["sueta_id"], message.from_user.id),
        ).fetchone()
        if not member:
            await message.answer("Сначала войди в эту суету.")
            await state.clear()
            return
        conn.execute(
            "INSERT INTO sueta_messages(sueta_id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
            (data["sueta_id"], message.from_user.id, text, datetime.now().isoformat(timespec="seconds")),
        )
    await state.clear()
    await message.answer("💬 Сообщение отправлено. Открой суету снова.", reply_markup=main_keyboard())


@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📍 <b>SUETA 05</b>\n\n"
        "Локальная соцсеть Дагестана внутри Telegram.\n\n"
        "В ленте — только посты и лайки.\n"
        "Общение — отдельно, в мини-суетах.\n"
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
