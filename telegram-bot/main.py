import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

CITY = "Буйнакск"
USERS_FILE = Path(__file__).resolve().parent / "users.json"
TOKEN_FILE = Path(__file__).resolve().parent.parent / "token.txt"

MORNING_WAKEUP_HOUR = 7
MORNING_WAKEUP_MINUTE = 30
AFTERNOON_CLOSE_HOUR = 14

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

dp = Dispatcher()
scheduler = AsyncIOScheduler()


def load_users() -> set[int]:
    if not USERS_FILE.exists():
        return set()
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return {int(user_id) for user_id in data}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        logger.exception("Не удалось прочитать users.json")
        return set()


def save_user(user_id: int) -> None:
    users = load_users()
    users.add(user_id)
    USERS_FILE.write_text(
        json.dumps(sorted(users), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_weather() -> str:
    return "🌤 +12°C, небольшой дождь. Днём до +15°C, ветер 2 м/с."


def get_currency() -> str:
    return "🇺🇸 Доллар: 80.67 ₽ | 🇪🇺 Евро: 89.81 ₽ | 🇨🇳 Юань: 12.08 ₽"


def get_news_russia() -> str:
    return (
        "1. <b>Гуманитарный конвой</b> входит в Алёшки: жителям доставят продукты.\n"
        "2. <b>Саммит Россия — Африка</b>: Путин проводит переговоры с лидерами.\n"
        "3. <b>Госдума</b> приняла в первом чтении проект бюджета на трёхлетку.\n"
        "4. <b>Дагестан</b>: Красный мост закрыт, объезд через Буйнакск.\n"
        "5. <b>35 лет Конституционному суду</b> РФ."
    )


def get_news_world() -> str:
    return (
        "1. <b>Ближний Восток</b>: ПВО Саудовской Аравии перехватила ракеты хуситов.\n"
        "2. <b>Евросоюз</b>: фон дер Ляйен предложила Канаде статус ассоциированного члена.\n"
        "3. <b>Испания</b>: число жертв столкновения поездов под Толедо снижено до 69."
    )


def get_morning_digest() -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    return (
        f"☀️ <b>Доброе утро! {CITY}, {today}</b>\n\n"
        f"<b>🌤 Погода</b>\n{get_weather()}\n\n"
        f"<b>💵 «По закону» (Курс ЦБ РФ)</b>\n{get_currency()}\n\n"
        f"<b>🇷🇺 Топ-5 новостей России</b>\n{get_news_russia()}\n\n"
        f"<b>🌍 Топ-3 новости мира</b>\n{get_news_world()}\n\n"
        "<i>Хорошего дня! Не забудьте выпить воды.</i>"
    )


def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить данные", callback_data="refresh")
    )
    return builder.as_markup()


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user:
        save_user(message.from_user.id)
    await message.answer(
        f"👋 Привет! Я бот «Утренняя суета» для города {CITY}.\n"
        "Нажми кнопку ниже, чтобы получить сводку.",
        reply_markup=get_main_keyboard(),
    )


@dp.callback_query(F.data == "refresh")
async def process_refresh(callback: types.CallbackQuery) -> None:
    now = datetime.now()
    if now.hour >= AFTERNOON_CLOSE_HOUR:
        await callback.answer(
            "⏰ Уже поздно, приходите завтра утром!", show_alert=True
        )
        if callback.message:
            await callback.message.answer(
                "Приходите завтра, я работаю только до обеда. 🌙"
            )
        return

    await callback.answer("Собираю данные...")
    if callback.message:
        await callback.message.edit_text(
            get_morning_digest(), reply_markup=get_main_keyboard()
        )


async def morning_broadcast(bot: Bot) -> None:
    users = load_users()
    if not users:
        return

    text = (
        "☀️ <b>Просыпайся! Утренняя суета настала!</b>\n\n"
        "Нажми кнопку ниже, чтобы узнать погоду, курсы и новости."
    )
    keyboard = get_main_keyboard()

    for user_id in users:
        try:
            await bot.send_message(user_id, text, reply_markup=keyboard)
            await asyncio.sleep(0.05)
        except Exception:
            logger.exception("Не удалось отправить сообщение пользователю %s", user_id)


def load_token() -> str:
    token = os.getenv("BOT_TOKEN", "").strip()
    if token:
        return token

    candidates = [
        TOKEN_FILE,
        Path.cwd() / "token.txt",
        Path(__file__).resolve().parent / "token.txt",
    ]

    checked = []
    for path in dict.fromkeys(candidates):
        checked.append(str(path))
        if not path.is_file():
            continue

        raw = path.read_text(encoding="utf-8-sig")
        token = raw.strip().strip('"').strip("'").strip()
        if token:
            logger.info("Токен загружен из %s", path)
            return token

    raise RuntimeError(
        "Не удалось прочитать непустой токен. Проверены файлы: "
        + ", ".join(checked)
        + ". Токен должен быть обычным текстом без BOT_TOKEN=."
    )


async def main() -> None:
    bot = Bot(
        token=load_token(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    scheduler.add_job(
        morning_broadcast,
        "cron",
        hour=MORNING_WAKEUP_HOUR,
        minute=MORNING_WAKEUP_MINUTE,
        args=[bot],
    )
    scheduler.start()

    logger.info(
        "Бот запущен. Утренняя побудка в %02d:%02d. Отбой в %02d:00.",
        MORNING_WAKEUP_HOUR,
        MORNING_WAKEUP_MINUTE,
        AFTERNOON_CLOSE_HOUR,
    )

    try:
        while True:
            try:
                await dp.start_polling(bot)
                break
            except Exception as exc:
                logger.exception(
                    "Не удалось подключиться к Telegram API. "
                    "Повтор через 15 секунд: %s",
                    exc,
                )
                await asyncio.sleep(15)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
