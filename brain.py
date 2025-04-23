import aiosqlite
from collections import deque
from datetime import datetime
import asyncio
import logging

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class QueueManager:
    def __init__(self, db_path="queue.db"):
        self.db_path = db_path
        self.queue = deque()  # Локальна копія черги
        self.user_names = {}  # Кеш імен користувачів
        self.join_times = {}  # Кеш часу входу

    async def startup(self):
        """Виконує асинхронну ініціалізацію під час запуску бота"""
        logger.info("Запуск ініціалізації бази даних")
        await self.init_db()

    async def init_db(self):
        """Ініціалізація бази даних і таблиці"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS queue (
                        user_id INTEGER PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        join_time TEXT NOT NULL
                    )
                """)
                await db.commit()
                logger.info("База даних ініціалізована")
                await self.load_queue()
        except Exception as e:
            logger.error(f"Помилка ініціалізації бази даних: {e}")
            raise

    async def load_queue(self):
        """Завантаження черги з бази даних"""
        self.queue.clear()
        self.user_names.clear()
        self.join_times.clear()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT user_id, user_name, join_time FROM queue ORDER BY position") as cursor:
                    async for row in cursor:
                        user_id, user_name, join_time = row
                        self.queue.append(user_id)
                        self.user_names[user_id] = user_name
                        self.join_times[user_id] = datetime.fromisoformat(join_time)
            logger.info("Черга успішно завантажена з бази даних")
        except Exception as e:
            logger.error(f"Помилка завантаження черги: {e}")

    async def save_queue(self):
        """Збереження черги в базу даних"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM queue")
                for i, user_id in enumerate(self.queue):
                    await db.execute(
                        "INSERT INTO queue (user_id, user_name, position, join_time) VALUES (?, ?, ?, ?)",
                        (user_id, self.user_names[user_id], i + 1, self.join_times[user_id].isoformat())
                    )
                await db.commit()
                logger.info("Черга успішно збережена в базі даних")
        except Exception as e:
            logger.error(f"Помилка збереження черги: {e}")

    def join_queue(self, user_id: int, user_name: str) -> str:
        """Додає користувача до черги"""
        if user_id not in self.queue:
            self.queue.append(user_id)
            self.user_names[user_id] = user_name
            self.join_times[user_id] = datetime.now()
            logger.info(f"Користувач {user_name} (ID: {user_id}) доданий до черги")
            return f"{user_name}, ви додані до черги. Ваш номер: {len(self.queue)}"
        logger.warning(f"Користувач {user_name} (ID: {user_id}) вже в черзі")
        return "Ви вже в черзі!"

    def leave_queue(self, user_id: int) -> str:
        """Видаляє користувача з черги"""
        if user_id in self.queue:
            self.queue.remove(user_id)
            user_name = self.user_names.pop(user_id)
            self.join_times.pop(user_id)
            logger.info(f"Користувач {user_name} (ID: {user_id}) покинув чергу")
            return f"{user_name}, ви покинули чергу."
        logger.warning(f"Користувач (ID: {user_id}) не в черзі")
        return "Вас немає в черзі!"

    def view_queue(self) -> str:
        """Повертає список учасників черги"""
        if not self.queue:
            logger.info("Черга порожня")
            return "Черга порожня."
        queue_list = "\n".join(f"{i+1}. {self.user_names[uid]}" for i, uid in enumerate(self.queue))
        logger.info("Запит на перегляд черги")
        return f"Поточна черга:\n{queue_list}"

    async def next_in_queue(self) -> tuple[str, list[int]]:
        """Викликає наступного користувача та повертає оновлені позиції"""
        if not self.queue:
            logger.info("Черга порожня при виклику наступного")
            return "Черга порожня.", []
        next_user = self.queue.popleft()
        next_name = self.user_names.pop(next_user)
        self.join_times.pop(next_user)
        updated_users = list(self.queue)
        logger.info(f"Наступний користувач: {next_name} (ID: {next_user})")
        return f"Наступний: {next_name}", updated_users

    async def notify_position(self, user_id: int) -> str:
        """Повертає повідомлення про поточну позицію користувача"""
        if user_id not in self.queue:
            logger.warning(f"Користувач (ID: {user_id}) не в черзі для сповіщення")
            return "Вас немає в черзі!"
        position = list(self.queue).index(user_id) + 1
        logger.info(f"Сповіщення позиції для {self.user_names[user_id]} (ID: {user_id}): {position}")
        return f"{self.user_names[user_id]}, ваша позиція в черзі: {position}"

    async def remind_first(self, bot, chat_id: int):
        """Нагадує першому користувачу через 1 хвилину"""
        if not self.queue:
            logger.info("Черга порожня, нагадування не потрібне")
            return
        await asyncio.sleep(60)
        if self.queue:
            first_user = self.queue[0]
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{self.user_names[first_user]}, ви перший у черзі! Будь ласка, підготуйтеся."
                )
                logger.info(f"Нагадування надіслано першому користувачу (ID: {first_user})")
            except Exception as e:
                logger.error(f"Помилка надсилання нагадування: {e}")

    def get_stats(self) -> str:
        """Повертає статистику черги"""
        if not self.queue:
            logger.info("Черга порожня, статистика недоступна")
            return "Черга порожня, немає даних для статистики."
        total_users = len(self.queue)
        avg_wait = sum((datetime.now() - self.join_times[uid]).total_seconds() / 60 
                       for uid in self.queue) / total_users if total_users else 0
        logger.info(f"Запит статистики: {total_users} користувачів, середній час очікування {avg_wait:.1f} хвилин")
        return (f"📊 Статистика черги:\n"
                f"Кількість учасників: {total_users}\n"
                f"Середній час очікування: {avg_wait:.1f} хвилин")