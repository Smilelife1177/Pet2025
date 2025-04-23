import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from brain import QueueManager
import logging

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Завантажуємо токен
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("Токен TELEGRAM_TOKEN не знайдено в .env файлі")
    raise ValueError("Токен TELEGRAM_TOKEN не знайдено в .env файлі")

# Ініціалізуємо бота та диспетчер
bot = Bot(token=TOKEN)
dp = Dispatcher()
queue_manager = QueueManager()

async def check_token():
    """Перевіряє, чи токен коректний"""
    try:
        bot_info = await bot.get_me()
        logger.info(f"Токен коректний. Бот: {bot_info.username} (ID: {bot_info.id})")
        return True
    except Exception as e:
        logger.error(f"Помилка перевірки токена: {e}")
        return False

async def disable_webhook():
    """Відключає вебхуки, щоб переконатися, що полінг працює"""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхуки відключені, полінг готовий до роботи")
    except Exception as e:
        logger.error(f"Помилка відключення вебхуків: {e}")

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Повертає основну клавіатуру з кнопками"""
    keyboard = [
        [InlineKeyboardButton(text="Записатися в чергу", callback_data='join')],
        [InlineKeyboardButton(text="Покинути чергу", callback_data='leave')],
        [InlineKeyboardButton(text="Переглянути чергу", callback_data='view')],
        [InlineKeyboardButton(text="Наступний!", callback_data='next')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обробник команди /start"""
    logger.info(f"Отримано команду /start від користувача {message.from_user.id} ({message.from_user.username})")
    await message.answer(
        "Вітаю! Це бот електронної черги. Оберіть дію:",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    """Обробник команди /stats"""
    logger.info(f"Отримано команду /stats від користувача {message.from_user.id} ({message.from_user.username})")
    stats = queue_manager.get_stats()
    await message.answer(stats, reply_markup=get_main_keyboard())

@dp.callback_query()
async def button_handler(callback: types.CallbackQuery):
    """Обробник натискань на кнопки"""
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name or "Анонім"
    chat_id = callback.message.chat.id
    logger.info(f"Отримано callback {callback.data} від користувача {user_id} ({callback.from_user.username})")

    try:
        if callback.data == 'join':
            response = queue_manager.join_queue(user_id, user_name)
            await queue_manager.save_queue()

        elif callback.data == 'leave':
            response = queue_manager.leave_queue(user_id)
            await queue_manager.save_queue()

        elif callback.data == 'view':
            response = queue_manager.view_queue()

        elif callback.data == 'next':
            response, updated_users = await queue_manager.next_in_queue()
            await queue_manager.save_queue()
            if queue_manager.queue:
                asyncio.create_task(queue_manager.remind_first(bot, chat_id))
            for uid in updated_users:
                notify_msg = await queue_manager.notify_position(uid)
                await bot.send_message(chat_id=chat_id, text=notify_msg)

        await callback.message.edit_text(response, reply_markup=get_main_keyboard())
        await callback.answer()
    except Exception as e:
        logger.error(f"Помилка обробки callback {callback.data}: {e}")
        await callback.message.edit_text("Виникла помилка. Спробуйте ще раз.")
        await callback.answer()

async def main():
    """Запуск бота"""
    try:
        logger.info("Запуск бота...")
        # Перевіряємо токен
        if not await check_token():
            raise ValueError("Некоректний токен. Перевірте TELEGRAM_TOKEN у .env")
        # Відключаємо вебхуки
        await disable_webhook()
        # Ініціалізуємо базу даних
        await queue_manager.startup()
        logger.info("База даних ініціалізована, починаємо полінг")
        # Запускаємо полінг
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Помилка запуску бота: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())