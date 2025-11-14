import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Включаем логирование для отслеживания ошибок
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    user = update.effective_user
    # Отправляем сообщение "Привет, Мир!" пользователю, который нажал /start
    await update.message.reply_text(f'Привет, {user.first_name}! Это простой тестовый бот. Мир!') # Используем имя пользователя для персонализации

def main() -> None:
    """Запускает бота."""
    # Создаём приложение и передаём ему токен вашего бота
    application = Application.builder().token('8006833399:AAEgxpBe6Mas6HW_RTgNTe0UmDPUBkJSkhM').build()

    # Регистрируем обработчик команды /start
    application.add_handler(CommandHandler("start", start))

    # Запускаем бота, используя long polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
