import os
import logging
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message with a button that opens the web app."""
    # Укажите адрес вашего Vercel приложения здесь
    web_app_url = "https://musicbotncei4.vercel.app/"
    
    keyboard = [
        [InlineKeyboardButton("Open Music MVP", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎧 Добро пожаловать в Music MVP!\n\nНажми на кнопку ниже, чтобы открыть приложение поиска музыки:",
        reply_markup=reply_markup
    )

def main() -> None:
    """Run the bot."""
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не найден в .env файле!")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    print("🤖 Бот запущен! Ожидание сообщений...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
