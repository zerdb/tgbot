import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f'Привет, {user.first_name}! Это простой тестовый бот.'
    )

def main() -> None:
    token = __import__('os').environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('Не задан TELEGRAM_BOT_TOKEN')
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
