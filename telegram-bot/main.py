import asyncio
import html
import logging
import os
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
    waiting_text = State()


class CommentStates(StatesGroup):
    waiting_text = State()


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS likes (
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(post_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(post_id, user_id)
        );
        """)


def register_user(user) -> None:
    if not user:
        return
    with db() as conn:
        conn.execute(
            """INSERT INTO users(user_id, username, first_name, joined_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name""",
            (user.id, user.username, user.first_name, datetime.now().isoformat(timespec="seconds")),
        )


def display_name(row) -> str:
    if row["username"]:
        return "@" + row["username"]
    return row["first_name"] or "Суетолог"


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


def feed(limit=10, offset=0):
    with db() as conn:
        return conn.execute("""
            SELECT p.*, u.username, u.first_name,
                   (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes,
                   (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) comments
            FROM posts p JOIN users u ON u.user_id=p.user_id
            ORDER BY p.id DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()


def post_text(row) -> str:
    text = html.escape(row["text"])
    return (
        f"🔥 <b>{display_name(row)}</b> · <i>{time_ago(row['created_at'])}</i>\n\n"
        f"{text}\n\n"
        f"❤️ {row['likes']}    💬 {row['comments']}"
    )


def main_keyboard():
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🔥 Лента", callback_data="feed:0"),
        InlineKeyboardButton(text="➕ Запостить", callback_data="post"),
    )
    b.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
        InlineKeyboardButton(text="📍 05", callback_data="about"),
    )
    return b.as_markup()


def post_keyboard(post_id: int, liked=False):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="❤️" if not liked else "💔", callback_data=f"like:{post_id}"),
        InlineKeyboardButton(text="💬 Коммент", callback_data=f"comment:{post_id}"),
        InlineKeyboardButton(text="🚩", callback_data=f"report:{post_id}"),
    )
    return b.as_markup()


def nav_keyboard(offset: int, has_next: bool):
    b = InlineKeyboardBuilder()
    buttons = []
    if offset > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Новее", callback_data=f"feed:{max(0, offset-10)}"))
    if has_next:
        buttons.append(InlineKeyboardButton(text="Старее ➡️", callback_data=f"feed:{offset+10}"))
    if buttons:
        b.row(*buttons)
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="home"))
    return b.as_markup()


def get_home_text() -> str:
    return (
        "🌀 <b>SUETA 05</b>\n\n"
        "Место, где Дагестан говорит сам за себя.\n"
        "Пиши, что происходит. Читай, что происходит.\n"
        "Без пафоса — просто суета.\n\n"
        "🔥 <b>Лента</b> — посты людей\n"
        "➕ <b>Запостить</b> — высказаться\n"
        "👤 <b>Профиль</b> — твоя активность\n"
        "📍 <b>05</b> — что это вообще"
    )


async def show_feed(message_or_callback, user_id: int, offset=0):
    rows = feed(offset=offset)
    if not rows:
        text = (
            "🔥 <b>Лента пока пустая</b>\n\n"
            "Будь первым, кто устроит суету. Нажми «➕ Запостить»."
        )
        markup = main_keyboard()
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(text, reply_markup=markup)
        else:
            await message_or_callback.answer(text, reply_markup=markup)
        return

    for index, row in enumerate(rows):
        with db() as conn:
            liked = conn.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?", (row["id"], user_id)).fetchone()
        markup = post_keyboard(row["id"], bool(liked))
        if index == 0 and isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(post_text(row), reply_markup=markup)
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.answer(post_text(row), reply_markup=markup)
        else:
            await message_or_callback.answer(post_text(row), reply_markup=markup)
    nav = nav_keyboard(offset, len(rows) == 10)
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.answer("Лента", reply_markup=nav)
    else:
        await message_or_callback.answer("Лента", reply_markup=nav)


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    register_user(message.from_user)
    await state.clear()
    await message.answer(get_home_text(), reply_markup=main_keyboard())


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


@dp.callback_query(F.data.startswith("feed:"))
async def open_feed(callback: types.CallbackQuery):
    await callback.answer()
    offset = int(callback.data.split(":")[1])
    await show_feed(callback, callback.from_user.id, offset)


@dp.callback_query(F.data == "post")
async def create_post(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PostStates.waiting_text)
    await callback.message.answer(
        "➕ <b>Новая суета</b>\n\n"
        "Напиши текст одним сообщением. Максимум 1000 символов.\n"
        "Фото и видео добавим следующим этапом."
    )


@dp.message(PostStates.waiting_text)
async def save_post(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пока принимаю только текстовый пост 👀")
        return
    text = message.text.strip()
    if not text:
        return
    if len(text) > 1000:
        await message.answer("Слишком много суеты 😄 Максимум 1000 символов.")
        return
    register_user(message.from_user)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO posts(user_id, text, created_at) VALUES (?, ?, ?)",
            (message.from_user.id, text, datetime.now().isoformat(timespec="seconds")),
        )
        post_id = cur.lastrowid
    await state.clear()
    await message.answer("🔥 <b>Пост опубликован!</b>", reply_markup=main_keyboard())
    await message.answer("Теперь он в ленте. Давай посмотрим:", reply_markup=InlineKeyboardBuilder().button(
        text="🔥 Открыть ленту", callback_data="feed:0"
    ).as_markup())


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
    with db() as conn:
        row = conn.execute("""
            SELECT p.*, u.username, u.first_name,
                   (SELECT COUNT(*) FROM likes WHERE post_id=p.id) likes,
                   (SELECT COUNT(*) FROM comments WHERE post_id=p.id) comments
            FROM posts p JOIN users u ON u.user_id=p.user_id WHERE p.id=?
        """, (post_id,)).fetchone()
    await callback.message.edit_text(post_text(row), reply_markup=post_keyboard(post_id, not bool(exists)))


@dp.callback_query(F.data.startswith("comment:"))
async def comment_start(callback: types.CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split(":")[1])
    await callback.answer()
    await state.update_data(post_id=post_id)
    await state.set_state(CommentStates.waiting_text)
    await callback.message.answer("💬 Напиши комментарий одним сообщением.")


@dp.message(CommentStates.waiting_text)
async def save_comment(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Только текстовый комментарий пока что.")
        return
    data = await state.get_data()
    post_id = data["post_id"]
    text = message.text.strip()
    if not text or len(text) > 500:
        await message.answer("Комментарий: от 1 до 500 символов.")
        return
    register_user(message.from_user)
    with db() as conn:
        conn.execute(
            "INSERT INTO comments(post_id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
            (post_id, message.from_user.id, text, datetime.now().isoformat(timespec="seconds")),
        )
    await state.clear()
    await message.answer("💬 Комментарий добавлен.", reply_markup=main_keyboard())


@dp.callback_query(F.data.startswith("report:"))
async def report(callback: types.CallbackQuery):
    post_id = int(callback.data.split(":")[1])
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO reports(post_id, user_id, created_at) VALUES (?, ?, ?)",
            (post_id, callback.from_user.id, datetime.now().isoformat(timespec="seconds")),
        )
    await callback.answer("🚩 Жалоба отправлена. Спасибо.", show_alert=True)


@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    register_user(callback.from_user)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (callback.from_user.id,)).fetchone()
        posts = conn.execute("SELECT COUNT(*) c FROM posts WHERE user_id=?", (callback.from_user.id,)).fetchone()["c"]
        likes = conn.execute(
            "SELECT COUNT(*) c FROM likes l JOIN posts p ON p.id=l.post_id WHERE p.user_id=?",
            (callback.from_user.id,),
        ).fetchone()["c"]
    name = display_name(user)
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>Профиль {name}</b>\n\n"
        f"🔥 Постов: <b>{posts}</b>\n"
        f"❤️ Лайков на твоих постах: <b>{likes}</b>\n\n"
        "Скоро сюда добавим аватар, город, подписки и личную статистику.",
        reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню", callback_data="home").as_markup(),
    )


@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📍 <b>05 — это Дагестан</b>\n\n"
        "Идея SUETA 05 — сделать местную социальную ленту прямо внутри Telegram.\n\n"
        "Сначала — текст, лайки, комментарии и жалобы.\n"
        "Потом — медиа, города, лички, подписки и настоящая общая суета.",
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
        while True:
            try:
                await dp.start_polling(bot)
                break
            except Exception as exc:
                logger.exception("Ошибка Telegram API. Повтор через 15 секунд: %s", exc)
                await asyncio.sleep(15)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
